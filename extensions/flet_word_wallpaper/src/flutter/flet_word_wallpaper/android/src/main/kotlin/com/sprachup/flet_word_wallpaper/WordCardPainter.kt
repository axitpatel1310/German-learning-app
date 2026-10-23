package com.sprachup.flet_word_wallpaper

import android.graphics.Canvas
import android.graphics.Color
import android.graphics.LinearGradient
import android.graphics.Paint
import android.graphics.RectF
import android.graphics.Shader
import android.graphics.Typeface
import android.text.Layout
import android.text.StaticLayout
import android.text.TextPaint
import android.util.DisplayMetrics
import android.util.TypedValue

/** Draws the whole wallpaper: a soft background and one word card in the middle. */
class WordCardPainter(private val metrics: DisplayMetrics) {

    private class Colors(
        val top: Int, val bottom: Int, val card: Int, val accent: Int,
        val text: Int, val muted: Int, val divider: Int,
    )

    private val light = Colors(
        top = 0xFFE8EAF6.toInt(), bottom = 0xFFF7F7FB.toInt(), card = Color.WHITE,
        accent = 0xFF3949AB.toInt(), text = 0xFF1B1B21.toInt(), muted = 0xFF5F5F6E.toInt(),
        divider = 0xFFE0E0EA.toInt(),
    )
    private val dark = Colors(
        top = 0xFF151829.toInt(), bottom = 0xFF0B0C12.toInt(), card = 0xFF1F2233.toInt(),
        accent = 0xFF9FA8FF.toInt(), text = 0xFFF1F1F6.toInt(), muted = 0xFFB0B2C3.toInt(),
        divider = 0xFF33374D.toInt(),
    )

    private fun sp(v: Float) = TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_SP, v, metrics)
    private fun dp(v: Float) = TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, v, metrics)

    private fun layout(text: String, size: Float, color: Int, width: Int, style: Int): StaticLayout {
        val paint = TextPaint(Paint.ANTI_ALIAS_FLAG).apply {
            textSize = sp(size)
            this.color = color
            typeface = Typeface.create(Typeface.DEFAULT, style)
        }
        return StaticLayout.Builder.obtain(text, 0, text.length, paint, width)
            .setAlignment(Layout.Alignment.ALIGN_NORMAL)
            .setLineSpacing(0f, 1.15f)
            .build()
    }

    fun paint(canvas: Canvas, word: WordCard, isDark: Boolean) {
        val c = if (isDark) dark else light
        val w = canvas.width.toFloat()
        val h = canvas.height.toFloat()

        val bg = Paint().apply {
            shader = LinearGradient(0f, 0f, 0f, h, c.top, c.bottom, Shader.TileMode.CLAMP)
        }
        canvas.drawRect(0f, 0f, w, h, bg)

        val cardWidth = minOf(w * 0.86f, dp(520f))
        val pad = dp(24f)
        val inner = (cardWidth - 2 * pad).toInt()
        val gap = dp(10f)

        // Card content, top to bottom.
        val blocks = buildList {
            if (word.tag.isNotBlank()) add(layout(word.tag.uppercase(), 12f, c.accent, inner, Typeface.BOLD))
            add(layout(word.headword, 34f, c.text, inner, Typeface.BOLD))
            if (word.english.isNotBlank()) add(layout(word.english, 19f, c.text, inner, Typeface.NORMAL))
        }
        val examples = buildList {
            if (word.exampleDe.isNotBlank()) add(layout(word.exampleDe, 17f, c.text, inner, Typeface.ITALIC))
            if (word.exampleEn.isNotBlank()) add(layout(word.exampleEn, 14f, c.muted, inner, Typeface.NORMAL))
        }
        val dividerSpace = if (examples.isEmpty()) 0f else dp(28f)
        val contentHeight = (blocks + examples).sumOf { it.height }.toFloat() +
            gap * (blocks.size + examples.size - 1).coerceAtLeast(0) + dividerSpace
        val cardHeight = contentHeight + 2 * pad

        // Centred, a little above the middle: clocks sit higher, app icons lower.
        val left = (w - cardWidth) / 2
        val top = (h * 0.48f - cardHeight / 2).coerceAtLeast(dp(24f))
        val card = RectF(left, top, left + cardWidth, top + cardHeight)
        val shadow = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.BLACK
            alpha = if (isDark) 90 else 28
        }
        canvas.drawRoundRect(RectF(card).apply { offset(0f, dp(4f)) }, dp(28f), dp(28f), shadow)
        canvas.drawRoundRect(card, dp(28f), dp(28f), Paint(Paint.ANTI_ALIAS_FLAG).apply { color = c.card })

        var y = top + pad
        fun draw(l: StaticLayout) {
            canvas.save()
            canvas.translate(left + pad, y)
            l.draw(canvas)
            canvas.restore()
            y += l.height + gap
        }
        blocks.forEach(::draw)
        if (examples.isNotEmpty()) {
            val mid = y - gap + dividerSpace / 2
            canvas.drawRect(left + pad, mid, left + cardWidth - pad, mid + dp(1f), Paint().apply { color = c.divider })
            y += dividerSpace - gap
            examples.forEach(::draw)
        }
    }
}
