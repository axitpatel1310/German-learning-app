package com.sprachup.flet_word_wallpaper

import android.app.PendingIntent
import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.view.View
import android.widget.RemoteViews

/**
 * Home-screen widget with one German word card, in a frosted-glass style. It shows a new
 * word every 30 minutes, and the arrow button skips to the next one. Tapping the card
 * opens the app.
 */
class WordWidgetProvider : AppWidgetProvider() {

    override fun onUpdate(context: Context, manager: AppWidgetManager, ids: IntArray) {
        // Called by the system every 30 minutes, but also when a widget is added or the
        // words change, so only move on once the current word has had its time.
        val store = WordStore(context, WordSource.WIDGET)
        if (System.currentTimeMillis() - store.shownAt() >= ROTATE_MS) store.next()
        ids.forEach { render(context, manager, it, store) }
    }

    override fun onAppWidgetOptionsChanged(
        context: Context, manager: AppWidgetManager, id: Int, options: Bundle,
    ) {
        render(context, manager, id, WordStore(context, WordSource.WIDGET))
    }

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action == ACTION_NEXT) {
            WordStore(context, WordSource.WIDGET).next()
            updateAll(context)
            return
        }
        super.onReceive(context, intent)
    }

    private class Colors(val accent: Int, val text: Int, val muted: Int, val divider: Int)

    companion object {
        private const val ACTION_NEXT = "com.sprachup.flet_word_wallpaper.NEXT_WORD"
        private const val ROTATE_MS = 25 * 60 * 1000L
        private const val COMPACT_DP = 130

        private val light = Colors(0xFF3949AB.toInt(), 0xFF1B1B21.toInt(), 0xFF5F5F6E.toInt(), 0x331B1B21)
        private val dark = Colors(0xFFB4BCFF.toInt(), 0xFFF4F4F8.toInt(), 0xFFB8BACB.toInt(), 0x33FFFFFF)

        fun ids(context: Context): IntArray = AppWidgetManager.getInstance(context)
            .getAppWidgetIds(ComponentName(context, WordWidgetProvider::class.java))

        fun updateAll(context: Context) {
            val manager = AppWidgetManager.getInstance(context)
            val store = WordStore(context, WordSource.WIDGET)
            ids(context).forEach { render(context, manager, it, store) }
        }

        private fun render(context: Context, manager: AppWidgetManager, id: Int, store: WordStore) {
            val word = store.current()
            val c = if (store.dark) dark else light
            val minHeight = manager.getAppWidgetOptions(id)
                .getInt(AppWidgetManager.OPTION_APPWIDGET_MIN_HEIGHT, 0)
            val compact = minHeight in 1 until COMPACT_DP

            val views = RemoteViews(context.packageName, R.layout.word_widget)
            views.setInt(
                R.id.widget_root, "setBackgroundResource",
                if (store.dark) R.drawable.word_widget_bg_dark else R.drawable.word_widget_bg_light,
            )
            fun text(viewId: Int, value: String, color: Int, show: Boolean = true) {
                views.setTextViewText(viewId, value)
                views.setTextColor(viewId, color)
                views.setViewVisibility(viewId, if (show && value.isNotBlank()) View.VISIBLE else View.GONE)
            }
            text(R.id.tag, word.tag.uppercase(), c.accent)
            text(R.id.headword, word.headword, c.text)
            text(R.id.english, word.english, c.text)
            val examples = !compact && word.exampleDe.isNotBlank()
            text(R.id.example_de, word.exampleDe, c.text, examples)
            text(R.id.example_en, word.exampleEn, c.muted, examples)
            views.setViewVisibility(R.id.divider, if (examples) View.VISIBLE else View.GONE)
            views.setInt(R.id.divider, "setBackgroundColor", c.divider)
            views.setInt(R.id.next, "setColorFilter", c.accent)

            views.setOnClickPendingIntent(R.id.next, PendingIntent.getBroadcast(
                context, 0,
                Intent(context, WordWidgetProvider::class.java).setAction(ACTION_NEXT),
                PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
            ))
            context.packageManager.getLaunchIntentForPackage(context.packageName)?.let {
                views.setOnClickPendingIntent(R.id.widget_root, PendingIntent.getActivity(
                    context, 0, it, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
                ))
            }
            manager.updateAppWidget(id, views)
        }
    }
}
