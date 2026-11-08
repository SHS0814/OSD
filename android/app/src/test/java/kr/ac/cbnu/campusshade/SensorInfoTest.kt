package kr.ac.cbnu.campusshade

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import java.time.OffsetDateTime

class SensorInfoTest {
    // /api/sensors properties as org.json hands them over: Int, Double, String.
    private val properties = mapOf<String, Any?>(
        "sensor" to "sensor 01",
        "team" to 2,
        "start" to "2026-09-28T00:00:08+09:00",
        "end" to "2026-10-04T23:59:39+09:00",
        "readings" to 52020,
        "temp_ok_pct" to 100.0,
        "co2_ok_pct" to 76.7,
    )

    @Test fun parsesEveryProperty() {
        val site = SensorInfo.parse("sensor 01", properties, 36.626906, 127.457722)!!
        assertEquals("sensor 01", site.id)
        assertEquals("sensor 01", site.name)
        assertEquals(2, site.team)
        assertEquals(OffsetDateTime.parse("2026-09-28T00:00:08+09:00"), site.recordStart)
        assertEquals(OffsetDateTime.parse("2026-10-04T23:59:39+09:00"), site.recordEnd)
        assertEquals(52020L, site.readings)
        assertEquals(100.0, site.tempOkPct!!, 0.0)
        assertEquals(76.7, site.co2OkPct!!, 0.0)
    }

    @Test fun missingOrNullPropertiesStayNull() {
        val site = SensorInfo.parse(null, mapOf("sensor" to "sensor 09", "team" to null, "start" to "not a date"), 1.0, 2.0)!!
        assertEquals("sensor 09", site.id)
        assertNull(site.team)
        assertNull(site.recordStart)
        assertNull(site.readings)
        assertNull(SensorInfo.parse(null, emptyMap(), 1.0, 2.0))
        assertEquals("s7", SensorInfo.parse("s7", emptyMap(), 1.0, 2.0)!!.name)
    }

    @Test fun findsByIdThenName() {
        val a = SensorInfo.parse("sensor 01", properties, 0.0, 0.0)!!
        val b = SensorInfo.parse("x", mapOf("sensor" to "sensor 04"), 0.0, 0.0)!!
        assertEquals(a, SensorInfo.find(listOf(a, b), "sensor 01", null))
        assertEquals(b, SensorInfo.find(listOf(a, b), "nope", "sensor 04"))
        assertNull(SensorInfo.find(listOf(a, b), null, null))
    }

    @Test fun readingsArePlaceholdersUntilThereIsAnApi() {
        val rows = SensorInfo.readingRows(null)
        assertEquals(listOf("기온", "습도", "CO₂", "측정 시각"), rows.map { it.first })
        rows.forEach { assertEquals(SensorInfo.PLACEHOLDER, it.second) }
    }

    @Test fun readingsFormatOnceFilled() {
        val reading = SensorReading(23.46, 61.0, 512.0, OffsetDateTime.parse("2026-10-01T05:30:00Z"))
        assertEquals(listOf("23.5°C", "61%", "512 ppm", "10/01 14:30"), SensorInfo.readingRows(reading).map { it.second })
        // Only what is known is filled.
        assertEquals(listOf("23.0°C", "—", "—", "—"), SensorInfo.readingRows(SensorReading(airTempC = 23.0)).map { it.second })
    }

    @Test fun siteRowsShowOnlyWhatIsKnown() {
        val full = SensorInfo.siteRows(SensorInfo.parse("sensor 01", properties, 36.626906, 127.457722)!!)
        assertEquals(
            listOf(
                "센서 ID" to "sensor 01",
                "실습 팀" to "2팀",
                "위치" to "36.62691, 127.45772",
                "기록 기간" to "09/28 ~ 10/04",
                "기록 수" to "52,020건",
                "기온 정상 비율" to "100%",
                "CO₂ 정상 비율" to "76.7%",
            ),
            full,
        )
        val bare = SensorInfo.siteRows(SensorSite("s1", "s1", 1.0, 2.0))
        assertEquals(listOf("센서 ID", "위치"), bare.map { it.first })
    }
}
