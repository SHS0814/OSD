package kr.ac.cbnu.campusshade

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.LinearGradient
import android.graphics.Paint
import android.graphics.Shader
import android.util.AttributeSet
import android.view.View
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.min
import kotlin.math.sin
import kotlin.random.Random

/**
 * Tints only the screen edges by the felt temperature where you stand: frost
 * (white–sky blue with ice crystals) when cold, an orange–red glow when hot. The
 * middle of the map stays clear. Not clickable, so touches go to the map below.
 * Changes fade once; nothing moves while a stage holds.
 */
class FeltEdgeView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
) : View(context, attrs) {
    private var stage: FeltStage = FeltStage.COMFORT
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG)
    private var frost: Bitmap? = null
    private val density = resources.displayMetrics.density

    init {
        isClickable = false
        isFocusable = false
        importantForAccessibility = IMPORTANT_FOR_ACCESSIBILITY_NO
        alpha = 0f
        setWillNotDraw(false)
    }

    /** Shows [next], fading out the old stage and in the new one only when it changes. */
    fun setStage(next: FeltStage) {
        if (next == stage) return
        animate().cancel()
        if (!stage.hasEffect) {
            stage = next
            invalidate()
            animate().alpha(1f).setDuration(FADE_MS).start()
        } else {
            animate().alpha(0f).setDuration(FADE_MS / 2).withEndAction {
                stage = next
                invalidate()
                if (next.hasEffect) animate().alpha(1f).setDuration(FADE_MS / 2).start()
            }.start()
        }
    }

    override fun onSizeChanged(w: Int, h: Int, oldw: Int, oldh: Int) {
        super.onSizeChanged(w, h, oldw, oldh)
        frost?.recycle()
        frost = null
    }

    override fun onDraw(canvas: Canvas) {
        if (!stage.hasEffect || width == 0 || height == 0) return
        val level = stage.level
        // Thicker and stronger edge with each level.
        val band = min(width, height) * (0.10f + 0.05f * level)
        val strength = 0.35f + 0.22f * level
        if (stage.cold) {
            drawEdges(canvas, band, Color.argb((200 * strength).toInt(), 235, 248, 255), Color.argb(0, 186, 230, 253))
            drawEdges(canvas, band * 0.45f, Color.argb((150 * strength).toInt(), 186, 230, 253), Color.argb(0, 186, 230, 253))
            paint.shader = null
            paint.alpha = (255 * strength).toInt().coerceAtMost(255)
            canvas.drawBitmap(frostBitmap(), 0f, 0f, paint)
            paint.alpha = 255
        } else {
            drawEdges(canvas, band, Color.argb((170 * strength).toInt(), 239, 68, 68), Color.argb(0, 249, 115, 22))
            drawEdges(canvas, band * 0.5f, Color.argb((150 * strength).toInt(), 249, 115, 22), Color.argb(0, 249, 115, 22))
        }
    }

    // A gradient strip along each edge, from [edge] at the border to [inner] [band] px in.
    private fun drawEdges(canvas: Canvas, band: Float, edge: Int, inner: Int) {
        val w = width.toFloat()
        val h = height.toFloat()
        paint.shader = LinearGradient(0f, 0f, 0f, band, edge, inner, Shader.TileMode.CLAMP)
        canvas.drawRect(0f, 0f, w, band, paint)
        paint.shader = LinearGradient(0f, h, 0f, h - band, edge, inner, Shader.TileMode.CLAMP)
        canvas.drawRect(0f, h - band, w, h, paint)
        paint.shader = LinearGradient(0f, 0f, band, 0f, edge, inner, Shader.TileMode.CLAMP)
        canvas.drawRect(0f, 0f, band, h, paint)
        paint.shader = LinearGradient(w, 0f, w - band, 0f, edge, inner, Shader.TileMode.CLAMP)
        canvas.drawRect(w - band, 0f, w, h, paint)
        paint.shader = null
    }

    // Ice crystals and speckles scattered near the edges, drawn once per size
    // with a fixed seed so the pattern stays put.
    private fun frostBitmap(): Bitmap {
        frost?.let { return it }
        val bitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
        val canvas = Canvas(bitmap)
        val random = Random(SEED)
        val stroke = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            style = Paint.Style.STROKE
            strokeCap = Paint.Cap.ROUND
        }
        val dot = Paint(Paint.ANTI_ALIAS_FLAG)
        val band = min(width, height) * 0.22f
        repeat(CRYSTALS) {
            val (x, y, depth) = edgePoint(random, band)
            // Fainter and smaller further from the edge.
            val fade = 1f - depth
            val radius = density * (4f + 9f * random.nextFloat()) * (0.5f + 0.5f * fade)
            stroke.color = Color.argb((210 * fade).toInt(), 255, 255, 255)
            stroke.strokeWidth = density * (0.6f + 0.6f * fade)
            val turn = random.nextFloat() * PI.toFloat()
            for (arm in 0 until 6) {
                val angle = turn + arm * PI.toFloat() / 3
                val ex = x + cos(angle) * radius
                val ey = y + sin(angle) * radius
                canvas.drawLine(x, y, ex, ey, stroke)
                // Two small barbs on each arm.
                val bx = x + cos(angle) * radius * 0.55f
                val by = y + sin(angle) * radius * 0.55f
                val barb = radius * 0.3f
                canvas.drawLine(bx, by, bx + cos(angle + 0.8f) * barb, by + sin(angle + 0.8f) * barb, stroke)
                canvas.drawLine(bx, by, bx + cos(angle - 0.8f) * barb, by + sin(angle - 0.8f) * barb, stroke)
            }
        }
        repeat(SPECKLES) {
            val (x, y, depth) = edgePoint(random, band)
            dot.color = Color.argb((180 * (1f - depth)).toInt(), 255, 255, 255)
            canvas.drawCircle(x, y, density * (0.5f + random.nextFloat()), dot)
        }
        frost = bitmap
        return bitmap
    }

    /** A random point within [band] of an edge, and how far in it is (0 at the edge, 1 at [band]). */
    private fun edgePoint(random: Random, band: Float): Triple<Float, Float, Float> {
        // Bias towards the edge: squaring a uniform number favours small depths.
        val depth = random.nextFloat().let { it * it }
        val along = random.nextFloat()
        val inset = depth * band
        return when (random.nextInt(4)) {
            0 -> Triple(along * width, inset, depth)
            1 -> Triple(along * width, height - inset, depth)
            2 -> Triple(inset, along * height, depth)
            else -> Triple(width - inset, along * height, depth)
        }
    }

    companion object {
        private const val FADE_MS = 500L
        private const val SEED = 20260113
        private const val CRYSTALS = 90
        private const val SPECKLES = 500
    }
}
