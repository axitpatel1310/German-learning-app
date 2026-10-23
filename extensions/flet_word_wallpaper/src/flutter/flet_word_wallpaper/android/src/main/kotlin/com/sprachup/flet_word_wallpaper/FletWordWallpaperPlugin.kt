package com.sprachup.flet_word_wallpaper

import android.app.WallpaperManager
import android.appwidget.AppWidgetManager
import android.content.ActivityNotFoundException
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.Handler
import android.os.Looper
import io.flutter.embedding.engine.plugins.FlutterPlugin
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel

/** Receives the word lists from the app, opens the wallpaper picker and pins the widget. */
class FletWordWallpaperPlugin : FlutterPlugin, MethodChannel.MethodCallHandler {
    private lateinit var channel: MethodChannel
    private lateinit var context: Context

    override fun onAttachedToEngine(binding: FlutterPlugin.FlutterPluginBinding) {
        context = binding.applicationContext
        channel = MethodChannel(binding.binaryMessenger, "flet_word_wallpaper")
        channel.setMethodCallHandler(this)
    }

    override fun onDetachedFromEngine(binding: FlutterPlugin.FlutterPluginBinding) {
        channel.setMethodCallHandler(null)
    }

    override fun onMethodCall(call: MethodCall, result: MethodChannel.Result) {
        when (call.method) {
            "setWords" -> saveWords(call, result, WordSource.WALLPAPER)
            "setWidgetWords" -> saveWords(call, result, WordSource.WIDGET)
            "openPicker" -> result.success(openPicker())
            "isActive" -> result.success(isActive())
            "pinWidget" -> result.success(pinWidget())
            "widgetCount" -> result.success(WordWidgetProvider.ids(context).size)
            else -> result.notImplemented()
        }
    }

    private fun saveWords(call: MethodCall, result: MethodChannel.Result, source: WordSource) {
        val json = call.argument<String>("json")
        if (json == null) {
            result.error("bad_args", "json is missing", null)
            return
        }
        // The list can be a few hundred kB: write it off the main thread.
        val main = Handler(Looper.getMainLooper())
        Thread {
            val ok = runCatching { WordStore.save(context, json, source) }.isSuccess
            main.post {
                if (ok && source == WordSource.WIDGET) WordWidgetProvider.updateAll(context)
                result.success(ok)
            }
        }.start()
    }

    /** Asks the launcher to add the widget (Android 8+, if the launcher supports it). */
    private fun pinWidget(): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return false
        val manager = AppWidgetManager.getInstance(context)
        if (!manager.isRequestPinAppWidgetSupported) return false
        return manager.requestPinAppWidget(
            ComponentName(context, WordWidgetProvider::class.java), null, null,
        )
    }

    private fun openPicker(): Boolean {
        val component = ComponentName(context, WordWallpaperService::class.java)
        val direct = Intent(WallpaperManager.ACTION_CHANGE_LIVE_WALLPAPER)
            .putExtra(WallpaperManager.EXTRA_LIVE_WALLPAPER_COMPONENT, component)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        val chooser = Intent(WallpaperManager.ACTION_LIVE_WALLPAPER_CHOOSER)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        for (intent in listOf(direct, chooser)) {
            try {
                context.startActivity(intent)
                return true
            } catch (e: ActivityNotFoundException) {
                // Some phones lack the direct preview screen; try the chooser next.
            }
        }
        return false
    }

    private fun isActive(): Boolean {
        val info = WallpaperManager.getInstance(context).wallpaperInfo ?: return false
        return info.packageName == context.packageName &&
            info.serviceName == WordWallpaperService::class.java.name
    }
}
