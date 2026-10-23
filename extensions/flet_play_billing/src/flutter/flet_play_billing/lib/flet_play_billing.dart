import 'package:flet/flet.dart';

import 'src/play_billing_service.dart';

class Extension extends FletExtension {
  @override
  FletService? createService(Control control) {
    switch (control.type) {
      case "PlayBilling":
        return PlayBillingService(control: control);
      default:
        return null;
    }
  }
}
