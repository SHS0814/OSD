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
