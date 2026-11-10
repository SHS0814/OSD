package kr.ac.cbnu.campusshade

import org.json.JSONArray
import org.json.JSONObject
import org.maplibre.android.geometry.LatLng

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
