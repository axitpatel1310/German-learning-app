package com.sprachup.flet_word_wallpaper

import android.content.Context
import org.json.JSONObject
import java.io.File
import java.util.Random

data class WordCard(
    val headword: String,
    val tag: String,
    val english: String,
    val exampleDe: String,
    val exampleEn: String,
)

/** Where a word list lives: the wallpaper and the widget each have their own. */
enum class WordSource(val fileName: String, val prefsName: String) {
    WALLPAPER("word_wallpaper.json", "flet_word_wallpaper"),
    WIDGET("word_widget.json", "flet_word_widget"),
}

/**
 * The words sent by the app (word_wallpaper.json or word_widget.json in the app's files
 * folder) and the position in them. Words come in a shuffled order that changes each
 * round, and the position survives restarts.
 */
class WordStore(private val context: Context, private val source: WordSource = WordSource.WALLPAPER) {
    private val prefs = context.getSharedPreferences(source.prefsName, Context.MODE_PRIVATE)
    private var loadedStamp = -1L
    private var words: List<WordCard> = emptyList()
    var dark = false
        private set

    fun current(): WordCard {
        reload()
        if (words.isEmpty()) return SAMPLE
        val index = prefs.getInt(KEY_INDEX, 0)
        val round = index / words.size
        val order = words.indices.toMutableList()
        order.shuffle(Random(prefs.getLong(KEY_SEED, 0L) + round))
        return words[order[index % words.size]]
    }

    fun next() {
        reload()
        if (words.isEmpty()) return
        prefs.edit()
            .putInt(KEY_INDEX, prefs.getInt(KEY_INDEX, 0) + 1)
            .putLong(KEY_SHOWN_AT, System.currentTimeMillis())
            .apply()
    }

    /** When the current word first appeared (start of the round for a fresh list). */
    fun shownAt(): Long = prefs.getLong(KEY_SHOWN_AT, 0L)

    private fun reload() {
        val file = file(context, source)
        val stamp = if (file.exists()) file.lastModified() + file.length() else 0L
        if (stamp == loadedStamp) return
        loadedStamp = stamp
        words = emptyList()
        if (!file.exists()) return
        runCatching {
            val root = JSONObject(file.readText())
            dark = root.optString("theme") == "dark"
            val list = root.getJSONArray("words")
            words = (0 until list.length()).map { i ->
                val w = list.getJSONObject(i)
                WordCard(
                    headword = w.optString("headword"),
                    tag = w.optString("tag"),
                    english = w.optString("english"),
                    exampleDe = w.optString("example_de"),
                    exampleEn = w.optString("example_en"),
                )
            }.filter { it.headword.isNotBlank() }
        }
    }

    companion object {
        private const val KEY_INDEX = "index"
        private const val KEY_SEED = "seed"
        private const val KEY_SHOWN_AT = "shown_at"

        val SAMPLE = WordCard(
            headword = "das Wort",
            tag = "A1 · noun (n)",
            english = "word",
            exampleDe = "Öffne Sprach Up und wähle deine Wörter aus.",
            exampleEn = "Open Sprach Up and choose your words.",
        )

        fun file(context: Context, source: WordSource) = File(context.filesDir, source.fileName)

        /** Replace the word list and start a fresh shuffled round. */
        fun save(context: Context, json: String, source: WordSource = WordSource.WALLPAPER) {
            JSONObject(json) // reject anything that isn't valid JSON
            val target = file(context, source)
            val tmp = File(target.parentFile, target.name + ".tmp")
            tmp.writeText(json)
            if (!tmp.renameTo(target)) {
                target.delete()
                tmp.renameTo(target)
            }
            val now = System.currentTimeMillis()
            context.getSharedPreferences(source.prefsName, Context.MODE_PRIVATE).edit()
                .putInt(KEY_INDEX, 0)
                .putLong(KEY_SEED, now)
                .putLong(KEY_SHOWN_AT, now)
                .apply()
        }
    }
}
