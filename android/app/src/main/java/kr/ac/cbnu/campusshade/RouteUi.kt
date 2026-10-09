package kr.ac.cbnu.campusshade

import org.json.JSONArray
import org.json.JSONObject
import org.maplibre.android.geometry.LatLng
import kotlin.math.abs
import kotlin.math.roundToInt

/** A place a route can start or end at: a building, or a point long-pressed on the map. */
data class Place(val name: String, val point: LatLng)

object Places {
    /** One place per named building, at the mean of its outline's corners. */
    fun fromBuildings(root: JSONObject): List<Place> {
        val features = root.getJSONArray("features")
        return (0 until features.length()).mapNotNull { index ->
            val feature = features.getJSONObject(index)
            val name = feature.optJSONObject("properties")?.optString("name").orEmpty()
            val geometry = feature.optJSONObject("geometry") ?: return@mapNotNull null
            val ring = outerRing(geometry) ?: return@mapNotNull null
            if (name.isBlank() || ring.length() < 2) return@mapNotNull null
            // The last corner repeats the first.
            val corners = (0 until ring.length() - 1).map { ring.getJSONArray(it) }
            Place(name, LatLng(corners.map { it.getDouble(1) }.average(), corners.map { it.getDouble(0) }.average()))
        }.sortedBy { it.name }
    }

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

object RouteSummary {
    private val labels = mapOf("shortest" to "최단", "balanced" to "균형", "coolest" to "그늘")

    /** Comparison lines for the route panel, one per route, plus a note when only the shortest is given. */
    fun text(root: JSONObject): String {
        val features = root.getJSONObject("routes").getJSONArray("features")
        val routes = (0 until features.length()).map { features.getJSONObject(it).getJSONObject("properties") }
        val shortest = routes.first()
        val lines = routes.map { route ->
            val label = labels[route.getString("kind")] ?: route.getString("kind")
            val length = if (route === shortest) {
                "${route.getDouble("length_m").roundToInt()} m · ${route.getDouble("walk_minutes").roundToInt()}분"
            } else {
                "+${route.getDouble("extra_m").roundToInt()} m"
            }
            val sun = route.getDouble("sun_minutes")
            val utci = route.optDouble("mean_utci", Double.NaN)
            val sunText = if (route === shortest) "햇빛 %.1f분".format(sun)
            else "햇빛 %.1f분 (%s)".format(sun, signed(sun - shortest.getDouble("sun_minutes"), "분"))
            val utciText = when {
                utci.isNaN() -> ""
                route === shortest -> " · 체감 %.1f°".format(utci)
                else -> " · 체감 %.1f° (%s)".format(utci, signed(utci - shortest.optDouble("mean_utci", utci), "°"))
            }
            "$label  $length · $sunText$utciText"
        }
        val note = when {
            routes.size > 1 -> null
            root.getJSONObject("solar").getDouble("altitude") <= 0 -> "해가 진 뒤라 그늘 차이가 없어 최단 경로만 보여요"
            shortest.optDouble("mean_utci", 0.0) <= 26.0 -> "쾌적한 날씨라 그늘로 돌아갈 필요가 없어요"
            else -> "이 구간에는 30% 안에서 더 시원한 길이 없어요"
        }
        return (lines + listOfNotNull(note)).joinToString("\n")
    }

    private fun signed(value: Double, unit: String): String =
        if (abs(value) < 0.05) "±0$unit" else "%+.1f%s".format(value, unit).replace("-", "−")
}
