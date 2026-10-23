package com.sprachup.flet_word_wallpaper

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.Build
import android.service.wallpaper.WallpaperService
import android.view.SurfaceHolder

/**
 * Live wallpaper with one German word card. The word moves on once per screen-off:
 * the next time the wallpaper becomes visible (lock screen or home screen after
 * turning the screen on) it shows a new word.
 */
class WordWallpaperService : WallpaperService() {
    override fun onCreateEngine(): Engine = WordEngine()

    inner class WordEngine : Engine() {
        private val store = WordStore(this@WordWallpaperService)
        private val painter = WordCardPainter(resources.displayMetrics)
        private var advance = false

        private val screenOff = object : BroadcastReceiver() {
            override fun onReceive(context: Context, intent: Intent) {
                advance = true
            }
        }

        override fun onCreate(surfaceHolder: SurfaceHolder) {
            super.onCreate(surfaceHolder)
            setTouchEventsEnabled(false)
            val filter = IntentFilter(Intent.ACTION_SCREEN_OFF)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                registerReceiver(screenOff, filter, Context.RECEIVER_NOT_EXPORTED)
            } else {
                registerReceiver(screenOff, filter)
            }
        }

        override fun onDestroy() {
            unregisterReceiver(screenOff)
            super.onDestroy()
        }

        override fun onVisibilityChanged(visible: Boolean) {
            if (!visible) return
            if (advance && !isPreview) {
                store.next()
                advance = false
            }
            draw()
        }

        override fun onSurfaceChanged(holder: SurfaceHolder, format: Int, width: Int, height: Int) {
            super.onSurfaceChanged(holder, format, width, height)
            draw()
        }

        override fun onSurfaceRedrawNeeded(holder: SurfaceHolder) {
            draw()
        }

        private fun draw() {
            val holder = surfaceHolder
            val canvas = runCatching { holder.lockCanvas() }.getOrNull() ?: return
            try {
                val word = store.current()
                painter.paint(canvas, word, store.dark)
            } finally {
                holder.unlockCanvasAndPost(canvas)
            }
        }
    }
}
