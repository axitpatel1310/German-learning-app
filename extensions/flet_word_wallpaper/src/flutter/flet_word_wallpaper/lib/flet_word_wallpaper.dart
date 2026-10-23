import 'package:flet/flet.dart';

import 'src/word_wallpaper_service.dart';

class Extension extends FletExtension {
  @override
  FletService? createService(Control control) {
    switch (control.type) {
      case "WordWallpaper":
        return WordWallpaperService(control: control);
      default:
        return null;
    }
  }
}
