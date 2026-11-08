package kr.ac.cbnu.campusshade

import kotlin.math.ceil
import kotlin.math.cos
import kotlin.math.floor
import kotlin.math.hypot

/**
 * The UTCI grid of /api/microclimate: [values] row-major from the north-west
 * corner, NaN outside campus. [corners] are (latitude, longitude) of the NW, NE,
 * SE and SW corners. Pure Kotlin so it can be unit tested.
 */
class UtciGrid(
    val rows: Int,
    val cols: Int,
    private val values: DoubleArray,
    corners: List<Pair<Double, Double>>,
) {
    private val originLat = corners[0].first
    private val originLon = corners[0].second
    private val metresPerDegLon = METRES_PER_DEG_LAT * cos(Math.toRadians(originLat))
    // Grid axes in local metres (east, north): along a row (to NE) and down the columns (to SW).
    private val colAxis = local(corners[1])
    private val rowAxis = local(corners[3])
    private val cellAlongCol = hypot(colAxis.first, colAxis.second) / cols
    private val cellAlongRow = hypot(rowAxis.first, rowAxis.second) / rows

    init {
        require(values.size == rows * cols) { "expected ${rows * cols} values, got ${values.size}" }
    }

    private fun local(point: Pair<Double, Double>): Pair<Double, Double> =
        (point.second - originLon) * metresPerDegLon to (point.first - originLat) * METRES_PER_DEG_LAT

    /** Fractional (row, column) of a point; whole numbers are cell edges. */
    fun cellOf(latitude: Double, longitude: Double): Pair<Double, Double> {
        val (x, y) = local(latitude to longitude)
        // Solve point = a * colAxis + b * rowAxis.
        val det = colAxis.first * rowAxis.second - colAxis.second * rowAxis.first
        val a = (x * rowAxis.second - y * rowAxis.first) / det
        val b = (colAxis.first * y - colAxis.second * x) / det
        return b * rows to a * cols
    }

    /**
     * Median UTCI of the cells whose centres lie within [radiusM] of the point (and
     * the cell under it), so GPS error does not jump between sun and shade. Null when
     * the point is off the grid or every such cell is outside campus.
     */
    fun medianAround(latitude: Double, longitude: Double, radiusM: Double = 10.0): Double? {
        val (row, col) = cellOf(latitude, longitude)
        if (row < 0 || col < 0 || row >= rows || col >= cols) return null
        val found = mutableListOf<Double>()
        val rowFrom = floor(row - radiusM / cellAlongRow).toInt().coerceAtLeast(0)
        val rowTo = ceil(row + radiusM / cellAlongRow).toInt().coerceAtMost(rows - 1)
        val colFrom = floor(col - radiusM / cellAlongCol).toInt().coerceAtLeast(0)
        val colTo = ceil(col + radiusM / cellAlongCol).toInt().coerceAtMost(cols - 1)
        for (r in rowFrom..rowTo) {
            for (c in colFrom..colTo) {
                val distance = hypot((r + 0.5 - row) * cellAlongRow, (c + 0.5 - col) * cellAlongCol)
                val under = r == row.toInt() && c == col.toInt()
                val value = values[r * cols + c]
                if ((distance <= radiusM || under) && !value.isNaN()) found += value
            }
        }
        if (found.isEmpty()) return null
        found.sort()
        val middle = found.size / 2
        return if (found.size % 2 == 1) found[middle] else (found[middle - 1] + found[middle]) / 2
    }

    companion object {
        private const val METRES_PER_DEG_LAT = 111_320.0
    }
}

/**
 * How the screen edge reacts to the felt temperature where you stand. 9 and 26 °C
 * bound UTCI "no thermal stress"; below it frost, above it a warm glow, each in
 * three strengths ([level] 1–3).
 */
enum class FeltStage(val level: Int, val cold: Boolean) {
    STRONG_COLD(3, true),
    MODERATE_COLD(2, true),
    SLIGHT_COLD(1, true),
    COMFORT(0, false),
    MODERATE_HEAT(1, false),
    STRONG_HEAT(2, false),
    VERY_STRONG_HEAT(3, false);

    val hasEffect: Boolean get() = level > 0

    companion object {
        fun of(utci: Double): FeltStage = when {
            utci < -13 -> STRONG_COLD
            utci < 0 -> MODERATE_COLD
            utci < 9 -> SLIGHT_COLD
            utci < 26 -> COMFORT
            utci < 32 -> MODERATE_HEAT
            utci < 38 -> STRONG_HEAT
            else -> VERY_STRONG_HEAT
        }

        /** UTCI stress band name, matching the heatmap legend. */
        fun label(utci: Double): String = when {
            utci >= 46 -> "극심한 더위"
            else -> when (of(utci)) {
                STRONG_COLD -> "강한 추위"
                MODERATE_COLD -> "보통 추위"
                SLIGHT_COLD -> "약한 추위"
                COMFORT -> "쾌적"
                MODERATE_HEAT -> "보통 더위"
                STRONG_HEAT -> "강한 더위"
                VERY_STRONG_HEAT -> "매우 강한 더위"
            }
        }
    }
}
