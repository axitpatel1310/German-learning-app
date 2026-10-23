import 'package:flet/flet.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

/// Forwards calls from the Python `WordWallpaper` service to the Android plugin.
/// On every other platform each call answers `false`.
class WordWallpaperService extends FletService {
  WordWallpaperService({required super.control});

  static const _channel = MethodChannel("flet_word_wallpaper");

  bool get _supported => !kIsWeb && defaultTargetPlatform == TargetPlatform.android;

  @override
  void init() {
    super.init();
    control.addInvokeMethodListener(_invokeMethod);
  }

  Future<dynamic> _invokeMethod(String name, dynamic args) async {
    if (name == "is_supported") return _supported;
    if (!_supported) return false;
    switch (name) {
      case "set_words":
        return _channel.invokeMethod<bool>("setWords", {"json": args["json"]});
      case "open_picker":
        return _channel.invokeMethod<bool>("openPicker");
      case "is_active":
        return _channel.invokeMethod<bool>("isActive");
      case "set_widget_words":
        return _channel.invokeMethod<bool>("setWidgetWords", {"json": args["json"]});
      case "pin_widget":
        return _channel.invokeMethod<bool>("pinWidget");
      case "widget_count":
        return _channel.invokeMethod<int>("widgetCount");
      default:
        throw Exception("Unknown WordWallpaper method: $name");
    }
  }

  @override
  void dispose() {
    control.removeInvokeMethodListener(_invokeMethod);
    super.dispose();
  }
}
