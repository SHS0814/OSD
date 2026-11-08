package kr.ac.cbnu.campusshade

import org.json.JSONArray
import org.json.JSONObject
import org.maplibre.android.geometry.LatLng
import kotlin.math.abs
import kotlin.math.roundToInt

/** A place a route can start or end at: a building, or a point long-pressed on the map. */
data class Place(val name: String, val point: LatLng)

object Places {
    /**
     * The searchable buildings in an /api/buildings response, each at the mean of
     * its outline's corners; unnamed ones are left out.
     */
    fun buildings(root: JSONObject): List<Building> {
        val features = root.getJSONArray("features")
        return (0 until features.length()).mapNotNull { index ->
            val feature = features.getJSONObject(index)
            val properties = feature.optJSONObject("properties")?.toMap() ?: return@mapNotNull null
            val geometry = feature.optJSONObject("geometry") ?: return@mapNotNull null
            val ring = outerRing(geometry) ?: return@mapNotNull null
            if (ring.length() < 2) return@mapNotNull null
            // The last corner repeats the first.
            val corners = (0 until ring.length() - 1).map { ring.getJSONArray(it) }
            BuildingSearch.fromProperties(properties, corners.map { it.getDouble(1) }.average(), corners.map { it.getDouble(0) }.average())
        }.sortedBy { it.label }.distinctBy { it.label }
    }

    /** The sensors in an /api/sensors response; features without a point are left out. */
    fun sensors(root: JSONObject): List<SensorSite> {
        val features = root.optJSONArray("features") ?: return emptyList()
        return (0 until features.length()).mapNotNull { index ->
            val feature = features.getJSONObject(index)
            val geometry = feature.optJSONObject("geometry")?.takeIf { it.optString("type") == "Point" }
            val point = geometry?.optJSONArray("coordinates")?.takeIf { it.length() >= 2 } ?: return@mapNotNull null
            SensorInfo.parse(
                feature.opt("id")?.takeUnless { it == JSONObject.NULL }?.toString(),
                feature.optJSONObject("properties")?.toMap().orEmpty(),
                point.getDouble(1),
                point.getDouble(0),
            )
        }
    }

    /** Top-level values only, JSON null as null. */
    private fun JSONObject.toMap(): Map<String, Any?> =
        keys().asSequence().associateWith { key -> opt(key).takeUnless { it == JSONObject.NULL } }

    private fun outerRing(geometry: JSONObject): JSONArray? = when (geometry.optString("type")) {
        "Polygon" -> geometry.getJSONArray("coordinates").getJSONArray(0)
        "MultiPolygon" -> geometry.getJSONArray("coordinates").getJSONArray(0).getJSONArray(0)
        else -> null
    }

    fun endpointsGeoJson(start: Place?, end: Place?): String {
        val features = listOfNotNull(start?.let { it to "start" }, end?.let { it to "end" }).map { (place, role) ->
            JSONObject()
                .put("type", "Feature")
                .put("geometry", JSONObject().put("type", "Point").put("coordinates", JSONArray().put(place.point.longitude).put(place.point.latitude)))
                .put("properties", JSONObject().put("role", role))
        }
        return JSONObject().put("type", "FeatureCollection").put("features", JSONArray(features)).toString()
    }
}

/** The numbers of one route in an /api/route response. */
data class RouteStats(
    val kind: String,
    val lengthM: Double,
    val extraM: Double,
    val walkMinutes: Double,
    val sunMinutes: Double,
    val coldMinutes: Double,
    val meanUtci: Double,
)

object RouteSummary {
    /** What the alternatives to the shortest route seek (/api/route "mode"). */
    const val MODE_HEAT = "heat"
    const val MODE_COLD = "cold"
    const val MODE_NONE = "none"

    /** Comparison lines for the route panel, one per route, plus a note when only the shortest is given. */
    fun text(root: JSONObject): String {
        val features = root.getJSONObject("routes").getJSONArray("features")
        val routes = (0 until features.length()).map {
            val p = features.getJSONObject(it).getJSONObject("properties")
            RouteStats(
                kind = p.getString("kind"),
                lengthM = p.getDouble("length_m"),
                extraM = p.optDouble("extra_m", 0.0),
                walkMinutes = p.getDouble("walk_minutes"),
                sunMinutes = p.getDouble("sun_minutes"),
                coldMinutes = p.optDouble("cold_minutes", 0.0),
                meanUtci = p.optDouble("mean_utci", Double.NaN),
            )
        }
        val altitude = root.getJSONObject("solar").getDouble("altitude")
        val mode = root.optString("mode").ifEmpty { legacyMode(routes, altitude) }
        return text(mode, routes, altitude)
    }

    // Servers before "mode" only looked for shade.
    private fun legacyMode(routes: List<RouteStats>, altitude: Double): String = when {
        routes.size > 1 -> MODE_HEAT
        altitude <= 0 || (routes.firstOrNull()?.meanUtci ?: 0.0) <= 26.0 -> MODE_NONE
        else -> MODE_HEAT
    }

    fun label(kind: String, mode: String): String = when (kind) {
        "shortest" -> "최단"
        "balanced" -> "균형"
        "coolest" -> if (mode == MODE_COLD) "햇볕길" else "그늘길"
        else -> kind
    }

    fun text(mode: String, routes: List<RouteStats>, solarAltitude: Double): String {
        val shortest = routes.first()
        val lines = routes.map { route ->
            val first = route === shortest
            val length = if (first) {
                "${route.lengthM.roundToInt()} m · ${route.walkMinutes.roundToInt()}분"
            } else {
                "+${route.extraM.roundToInt()} m"
            }
            val sunText = if (first) "햇빛 %.1f분".format(route.sunMinutes)
            else "햇빛 %.1f분 (%s)".format(route.sunMinutes, signed(route.sunMinutes - shortest.sunMinutes, "분"))
            val detail = if (mode == MODE_COLD) {
                // 추울 때는 햇빛이 늘고 추운 구간이 줄어드는 것이 이득이다.
                if (first) " · 추운 구간 %.1f분".format(route.coldMinutes)
                else " · 추운 구간 %.1f분 (%s)".format(route.coldMinutes, signed(route.coldMinutes - shortest.coldMinutes, "분"))
            } else {
                when {
                    route.meanUtci.isNaN() -> ""
                    first -> " · 체감 %.1f°".format(route.meanUtci)
                    else -> {
                        val base = if (shortest.meanUtci.isNaN()) route.meanUtci else shortest.meanUtci
                        " · 체감 %.1f° (%s)".format(route.meanUtci, signed(route.meanUtci - base, "°"))
                    }
                }
            }
            "${label(route.kind, mode)}  $length · $sunText$detail"
        }
        val note = when {
            routes.size > 1 -> null
            mode == MODE_NONE && solarAltitude <= 0 -> "해가 진 뒤라 양지·그늘 차이가 없어 최단 경로만 보여요"
            mode == MODE_NONE -> "쾌적한 날씨라 돌아갈 필요가 없어요"
            mode == MODE_COLD -> "이 구간에는 30% 안에서 더 따뜻한 길이 없어요"
            else -> "이 구간에는 30% 안에서 더 시원한 길이 없어요"
        }
        return (lines + listOfNotNull(note)).joinToString("\n")
    }

    private fun signed(value: Double, unit: String): String =
        if (abs(value) < 0.05) "±0$unit" else "%+.1f%s".format(value, unit).replace("-", "−")
}
