import 'dart:async';

import 'package:flet/flet.dart';
import 'package:flutter/foundation.dart';
import 'package:in_app_purchase/in_app_purchase.dart';

/// Buys the Premium product on Google Play for the Python `PlayBilling` service.
///
/// The purchase is not consumed here: the app sends its token to the accounts server, which
/// checks it with Google and consumes it. Until then it stays in [_unconfirmed], so it can be
/// sent again (`pending`) if the app closed or was offline.
class PlayBillingService extends FletService {
  PlayBillingService({required super.control});

  final _iap = InAppPurchase.instance;
  final Map<String, PurchaseDetails> _unconfirmed = {};
  StreamSubscription<List<PurchaseDetails>>? _sub;
  Completer<Map<String, dynamic>>? _buying;

  bool get _supported => !kIsWeb && defaultTargetPlatform == TargetPlatform.android;

  @override
  void init() {
    super.init();
    control.addInvokeMethodListener(_invokeMethod);
    if (_supported) {
      _sub = _iap.purchaseStream.listen(
        _onPurchases,
        onError: (Object e) => _answer({"status": "error", "message": "$e"}),
      );
    }
  }

  void _onPurchases(List<PurchaseDetails> purchases) {
    for (final p in purchases) {
      switch (p.status) {
        case PurchaseStatus.purchased:
        case PurchaseStatus.restored:
          final token = p.verificationData.serverVerificationData;
          _unconfirmed[token] = p;
          _answer({"status": "purchased", "purchase_token": token, "product_id": p.productID});
        case PurchaseStatus.pending:
          _answer({"status": "pending"});
        case PurchaseStatus.canceled:
          _answer({"status": "cancelled"});
        case PurchaseStatus.error:
          _answer({"status": "error", "message": p.error?.message ?? ""});
      }
    }
  }

  void _answer(Map<String, dynamic> result) {
    final buying = _buying;
    _buying = null;
    if (buying != null && !buying.isCompleted) buying.complete(result);
  }

  Future<dynamic> _invokeMethod(String name, dynamic args) async {
    if (name == "is_supported") return _supported && await _iap.isAvailable();
    if (!_supported) return null;
    switch (name) {
      case "buy":
        return _buy(args["product_id"] as String, args["account_ref"] as String);
      case "pending":
        return _pending();
      case "finish":
        final p = _unconfirmed.remove(args["purchase_token"]);
        if (p != null && p.pendingCompletePurchase) {
          try {
            await _iap.completePurchase(p);
          } catch (_) {
            // Already consumed by the server, which also counts as acknowledged.
          }
        }
        return true;
      default:
        throw Exception("Unknown PlayBilling method: $name");
    }
  }

  Future<Map<String, dynamic>> _buy(String productId, String accountRef) async {
    if (!await _iap.isAvailable()) {
      return {"status": "error", "message": "Google Play is not available on this device."};
    }
    final found = await _iap.queryProductDetails({productId});
    if (found.productDetails.isEmpty) {
      return {"status": "error", "message": "Premium was not found in Google Play."};
    }
    final buying = Completer<Map<String, dynamic>>();
    _buying = buying;
    final param = PurchaseParam(
      productDetails: found.productDetails.first,
      applicationUserName: accountRef, // becomes obfuscatedAccountId, checked by the server
    );
    final started = await _iap.buyConsumable(purchaseParam: param, autoConsume: false);
    if (!started) _answer({"status": "error", "message": "The purchase could not be started."});
    return buying.future;
  }

  Future<List<Map<String, dynamic>>> _pending() async {
    // Asks Play for purchases it still holds for this user; they arrive on the stream.
    await _iap.restorePurchases();
    await Future.delayed(const Duration(seconds: 2));
    return _unconfirmed.entries
        .map((e) => {"purchase_token": e.key, "product_id": e.value.productID})
        .toList();
  }

  @override
  void dispose() {
    _sub?.cancel();
    control.removeInvokeMethodListener(_invokeMethod);
    super.dispose();
  }
}
