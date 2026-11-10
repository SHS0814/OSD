package kr.ac.cbnu.campusshade.ui

import android.view.Gravity
import android.view.View
import android.widget.LinearLayout
import android.widget.TextView
import androidx.core.graphics.ColorUtils
import kr.ac.cbnu.campusshade.UtciPalette

/** The UTCI stress bands under the map, in the heatmap's colours; shown with the heatmap only. */
class Legend(private val container: LinearLayout) {
    init {
        val density = container.resources.displayMetrics.density
        UtciPalette.legend.forEach { (label, value) ->
            val background = UtciPalette.colorFor(value)
            container.addView(
                TextView(container.context).apply {
                    text = label
                    textSize = 10f
                    gravity = Gravity.CENTER
                    setBackgroundColor(background)
                    setTextColor(
                        if (ColorUtils.calculateLuminance(background) > 0.45) 0xFF1F2937.toInt()
                        else 0xFFFFFFFF.toInt()
                    )
                    setPadding(0, (3 * density).toInt(), 0, (3 * density).toInt())
                },
                LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f),
            )
        }
    }

    fun setVisible(visible: Boolean) {
        container.visibility = if (visible) View.VISIBLE else View.GONE
    }
}
