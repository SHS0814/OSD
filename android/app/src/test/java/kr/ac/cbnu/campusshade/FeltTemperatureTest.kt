package kr.ac.cbnu.campusshade

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.math.cos

class FeltTemperatureTest {
    @Test fun stageBoundaries() {
        assertEquals(FeltStage.STRONG_COLD, FeltStage.of(-13.1))
        assertEquals(FeltStage.MODERATE_COLD, FeltStage.of(-13.0))
        assertEquals(FeltStage.MODERATE_COLD, FeltStage.of(-0.1))
        assertEquals(FeltStage.SLIGHT_COLD, FeltStage.of(0.0))
        assertEquals(FeltStage.SLIGHT_COLD, FeltStage.of(8.9))
        assertEquals(FeltStage.COMFORT, FeltStage.of(9.0))
        assertEquals(FeltStage.COMFORT, FeltStage.of(25.9))
        assertEquals(FeltStage.MODERATE_HEAT, FeltStage.of(26.0))
        assertEquals(FeltStage.MODERATE_HEAT, FeltStage.of(31.9))
        assertEquals(FeltStage.STRONG_HEAT, FeltStage.of(32.0))
        assertEquals(FeltStage.STRONG_HEAT, FeltStage.of(37.9))
        assertEquals(FeltStage.VERY_STRONG_HEAT, FeltStage.of(38.0))
        assertEquals(FeltStage.VERY_STRONG_HEAT, FeltStage.of(50.0))
    }

    @Test fun stageLevels() {
        assertFalse(FeltStage.COMFORT.hasEffect)
        assertEquals(listOf(3, 2, 1), listOf(FeltStage.of(-20.0), FeltStage.of(-5.0), FeltStage.of(5.0)).map { it.level })
        assertTrue(FeltStage.of(5.0).cold)
        assertEquals(listOf(1, 2, 3), listOf(FeltStage.of(30.0), FeltStage.of(35.0), FeltStage.of(40.0)).map { it.level })
        assertFalse(FeltStage.of(30.0).cold)
    }

    @Test fun labelsMatchLegend() {
        assertEquals("강한 추위", FeltStage.label(-20.0))
        assertEquals("보통 추위", FeltStage.label(-5.0))
        assertEquals("약한 추위", FeltStage.label(5.0))
        assertEquals("쾌적", FeltStage.label(20.0))
        assertEquals("보통 더위", FeltStage.label(31.0))
        assertEquals("강한 더위", FeltStage.label(33.0))
        assertEquals("매우 강한 더위", FeltStage.label(40.0))
        assertEquals("극심한 더위", FeltStage.label(47.0))
    }

    // A 10 x 10 grid of 4 m cells whose north-west corner is at (36, 127).
    private val cell = 4.0
    private val degLat = cell / 111_320.0
    private val degLon = cell / (111_320.0 * cos(Math.toRadians(36.0)))
    private fun grid(values: DoubleArray) = UtciGrid(
        10, 10, values,
        listOf(36.0 to 127.0, 36.0 to 127.0 + 10 * degLon, 36.0 - 10 * degLat to 127.0 + 10 * degLon, 36.0 - 10 * degLat to 127.0),
    )
    private fun centre(row: Int, col: Int) = (36.0 - (row + 0.5) * degLat) to (127.0 + (col + 0.5) * degLon)

    @Test fun locatesCells() {
        val g = grid(DoubleArray(100))
        val (lat, lon) = centre(3, 7)
        val (row, col) = g.cellOf(lat, lon)
        assertEquals(3.5, row, 1e-6)
        assertEquals(7.5, col, 1e-6)
    }

    @Test fun medianOfNearbyCells() {
        // Each cell holds its column number, so the median sits at the centre column.
        val g = grid(DoubleArray(100) { (it % 10).toDouble() })
        val (lat, lon) = centre(5, 5)
        assertEquals(5.0, g.medianAround(lat, lon, 10.0)!!, 1e-9)
        // A tiny radius uses only the cell underneath.
        assertEquals(5.0, g.medianAround(lat, lon, 0.5)!!, 1e-9)
    }

    @Test fun medianIgnoresOutsideCampus() {
        val values = DoubleArray(100) { Double.NaN }
        values[5 * 10 + 5] = 30.0
        values[5 * 10 + 6] = 34.0
        val g = grid(values)
        val (lat, lon) = centre(5, 5)
        assertEquals(32.0, g.medianAround(lat, lon, 10.0)!!, 1e-9)
    }

    @Test fun nullOffGridOrOutsideCampus() {
        val g = grid(DoubleArray(100) { Double.NaN })
        val (lat, lon) = centre(5, 5)
        assertNull(g.medianAround(lat, lon))
        val full = grid(DoubleArray(100) { 20.0 })
        assertNull(full.medianAround(36.001, 127.0))
        assertNull(full.medianAround(lat, 126.999))
    }
}
