package kr.ac.cbnu.campusshade

import android.graphics.Bitmap
import android.graphics.Color
import org.json.JSONArray
import org.json.JSONObject
import org.maplibre.android.geometry.LatLng
import org.maplibre.android.geometry.LatLngQuad

/** Colours for the UTCI (felt temperature) heatmap and its legend. */
object UtciPalette {
    // Continuous ramp; each heat stop sits at the centre of its UTCI stress band so
    // shade and sun inside one band still read as different colours.
    private val stops = listOf(
        -10.0 to Color.rgb(49, 54, 149),
        4.0 to Color.rgb(116, 173, 209),
        17.0 to Color.rgb(102, 189, 99),
        29.0 to Color.rgb(254, 224, 139),
        35.0 to Color.rgb(253, 174, 97),
        42.0 to Color.rgb(215, 48, 39),
        48.0 to Color.rgb(127, 0, 0),
    )

    /** UTCI stress bands shown in the legend: label and the value used for its swatch. */
    val legend = listOf(
        "추위\n<9" to 0.0,
        "쾌적\n9–26" to 17.0,
        "보통\n26–32" to 29.0,
        "강함\n32–38" to 35.0,
        "매우 강함\n38–46" to 42.0,
        "극심\n46+" to 48.0,
    )

    fun colorFor(value: Double): Int {
        if (value <= stops.first().first) return stops.first().second
        if (value >= stops.last().first) return stops.last().second
        val upper = stops.indexOfFirst { it.first >= value }
        val (lowValue, lowColor) = stops[upper - 1]
        val (highValue, highColor) = stops[upper]
        val t = ((value - lowValue) / (highValue - lowValue)).toFloat()
        return Color.rgb(
            lerp(Color.red(lowColor), Color.red(highColor), t),
            lerp(Color.green(lowColor), Color.green(highColor), t),
            lerp(Color.blue(lowColor), Color.blue(highColor), t),
        )
    }

    private fun lerp(a: Int, b: Int, t: Float) = (a + (b - a) * t).toInt()
}

class UtciHeatmap(val quad: LatLngQuad, val bitmap: Bitmap) {
    companion object {
        /** One pixel per grid cell; cells outside campus or inside buildings stay transparent. */
        fun fromResponse(root: JSONObject): UtciHeatmap {
            val grid = root.getJSONObject("grid")
            val rows = grid.getInt("rows")
            val cols = grid.getInt("cols")
            val values = root.getJSONArray("utci")
            val pixels = IntArray(rows * cols) { index ->
                if (values.isNull(index)) Color.TRANSPARENT
                else UtciPalette.colorFor(values.getDouble(index))
            }
            val bitmap = Bitmap.createBitmap(pixels, cols, rows, Bitmap.Config.ARGB_8888)
            val corners = grid.getJSONArray("corners_wgs84")
            val quad = LatLngQuad(
                corners.latLng(0), corners.latLng(1), corners.latLng(2), corners.latLng(3),
            )
            return UtciHeatmap(quad, bitmap)
        }

        private fun JSONArray.latLng(index: Int): LatLng {
            val point = getJSONArray(index)
            return LatLng(point.getDouble(1), point.getDouble(0))
        }
    }
}
