package kr.ac.cbnu.campusshade

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class RouteSummaryTest {
    private fun route(kind: String, length: Double, sun: Double, cold: Double = 0.0, utci: Double = 30.0) =
        RouteStats(kind, length, length - 300.0, length / 72.0, sun, cold, utci)

    @Test fun labelsFollowMode() {
        assertEquals("그늘길", RouteSummary.label("coolest", "heat"))
        assertEquals("햇볕길", RouteSummary.label("coolest", "cold"))
        assertEquals("균형", RouteSummary.label("balanced", "cold"))
        assertEquals("최단", RouteSummary.label("shortest", "none"))
    }

    @Test fun coldModeShowsSunGainAndColdLoss() {
        val text = RouteSummary.text("cold", listOf(route("shortest", 300.0, 1.0, 3.0), route("coolest", 360.0, 3.5, 1.0)), 20.0)
        val lines = text.lines()
        assertEquals("최단  300 m · 4분 · 햇빛 1.0분 · 추운 구간 3.0분", lines[0])
        assertEquals("햇볕길  +60 m · 햇빛 3.5분 (+2.5분) · 추운 구간 1.0분 (−2.0분)", lines[1])
    }

    @Test fun heatModeKeepsFeltTemperature() {
        val text = RouteSummary.text("heat", listOf(route("shortest", 300.0, 3.0, utci = 33.0), route("coolest", 330.0, 1.0, utci = 31.5)), 50.0)
        assertTrue(text.lines()[1], text.lines()[1].startsWith("그늘길  +30 m · 햇빛 1.0분 (−2.0분) · 체감 31.5° (−1.5°)"))
    }

    @Test fun notesWhenOnlyShortest() {
        val one = listOf(route("shortest", 300.0, 1.0))
        assertEquals("해가 진 뒤라 양지·그늘 차이가 없어 최단 경로만 보여요", RouteSummary.text("none", one, -3.0).lines().last())
        assertEquals("쾌적한 날씨라 돌아갈 필요가 없어요", RouteSummary.text("none", one, 30.0).lines().last())
        assertEquals("이 구간에는 30% 안에서 더 시원한 길이 없어요", RouteSummary.text("heat", one, 30.0).lines().last())
        assertEquals("이 구간에는 30% 안에서 더 따뜻한 길이 없어요", RouteSummary.text("cold", one, 30.0).lines().last())
        assertEquals(2, RouteSummary.text("heat", one, 30.0).lines().size)
    }
}
