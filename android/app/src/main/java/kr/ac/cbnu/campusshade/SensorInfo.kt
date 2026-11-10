package kr.ac.cbnu.campusshade

import java.text.NumberFormat
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale

/**
 * Where one campus environment sensor stands, from a /api/sensors feature.
 * Every field but the name and position is optional: the server only adds what
 * scripts/build_sensor_sites.py found in the sensor's record.
 */
data class SensorSite(
    val id: String,
    val name: String,
    val latitude: Double,
    val longitude: Double,
    /** 실습 배정표의 팀 번호 */
    val team: Int? = null,
    val recordStart: OffsetDateTime? = null,
    val recordEnd: OffsetDateTime? = null,
    /** Readings in the record the position was taken from. */
    val readings: Long? = null,
    /** Share of readings that passed the quality checks, in percent. */
    val tempOkPct: Double? = null,
    val co2OkPct: Double? = null,
)

/**
 * One sensor's latest measurement. There is no readings API yet, so the app
 * passes null and the sheet shows placeholders; fill this in once there is.
 */
data class SensorReading(
    val airTempC: Double? = null,
    val humidityPct: Double? = null,
    val co2Ppm: Double? = null,
    val measuredAt: OffsetDateTime? = null,
)

/** Parsing and display rows for the sensor sheet. Pure Kotlin so it can be unit tested. */
object SensorInfo {
    const val PLACEHOLDER = "—"
    private val SEOUL = ZoneId.of("Asia/Seoul")
    private val MONTH_DAY = DateTimeFormatter.ofPattern("MM/dd")
    private val MONTH_DAY_TIME = DateTimeFormatter.ofPattern("MM/dd HH:mm")

    /**
     * The sensor from a feature's [featureId] and [properties] (JSON values as
     * Kotlin ones, null for JSON null), at [latitude], [longitude]; null when it
     * has neither an id nor a name.
     */
    fun parse(featureId: String?, properties: Map<String, Any?>, latitude: Double, longitude: Double): SensorSite? {
        val name = (properties["sensor"] as? String)?.trim()?.takeIf { it.isNotEmpty() }
        val id = featureId?.trim()?.takeIf { it.isNotEmpty() } ?: name ?: return null
        return SensorSite(
            id = id,
            name = name ?: id,
            latitude = latitude,
            longitude = longitude,
            team = (properties["team"] as? Number)?.toInt(),
            recordStart = time(properties["start"]),
            recordEnd = time(properties["end"]),
            readings = (properties["readings"] as? Number)?.toLong(),
            tempOkPct = (properties["temp_ok_pct"] as? Number)?.toDouble(),
            co2OkPct = (properties["co2_ok_pct"] as? Number)?.toDouble(),
        )
    }

    private fun time(value: Any?): OffsetDateTime? =
        (value as? String)?.let { runCatching { OffsetDateTime.parse(it) }.getOrNull() }

    /** The tapped sensor: by feature id first, then by its "sensor" name. */
    fun find(sites: List<SensorSite>, featureId: String?, name: String?): SensorSite? =
        sites.firstOrNull { featureId != null && it.id == featureId }
            ?: sites.firstOrNull { name != null && it.name == name }

    /** Measurement rows; every value is [PLACEHOLDER] until there is a [reading]. */
    fun readingRows(reading: SensorReading?): List<Pair<String, String>> = listOf(
        "기온" to (reading?.airTempC?.let { "%.1f°C".format(Locale.ROOT, it) } ?: PLACEHOLDER),
        "습도" to (reading?.humidityPct?.let { "%.0f%%".format(Locale.ROOT, it) } ?: PLACEHOLDER),
        "CO₂" to (reading?.co2Ppm?.let { "%.0f ppm".format(Locale.ROOT, it) } ?: PLACEHOLDER),
        "측정 시각" to (reading?.measuredAt?.let { it.atZoneSameInstant(SEOUL).format(MONTH_DAY_TIME) } ?: PLACEHOLDER),
    )

    /** Rows about the site, only for what the server sent. */
    fun siteRows(site: SensorSite): List<Pair<String, String>> {
        val rows = mutableListOf("센서 ID" to site.id)
        site.team?.let { rows += "실습 팀" to "${it}팀" }
        rows += "위치" to "%.5f, %.5f".format(Locale.ROOT, site.latitude, site.longitude)
        val start = site.recordStart?.atZoneSameInstant(SEOUL)?.format(MONTH_DAY)
        val end = site.recordEnd?.atZoneSameInstant(SEOUL)?.format(MONTH_DAY)
        if (start != null || end != null) rows += "기록 기간" to "${start ?: "?"} ~ ${end ?: "?"}"
        site.readings?.let { rows += "기록 수" to NumberFormat.getIntegerInstance(Locale.KOREA).format(it) + "건" }
        site.tempOkPct?.let { rows += "기온 정상 비율" to percent(it) }
        site.co2OkPct?.let { rows += "CO₂ 정상 비율" to percent(it) }
        return rows
    }

    private fun percent(value: Double): String =
        if (value % 1.0 == 0.0) "%.0f%%".format(Locale.ROOT, value) else "%.1f%%".format(Locale.ROOT, value)
}
