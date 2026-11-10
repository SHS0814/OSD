package kr.ac.cbnu.campusshade

import org.json.JSONArray
import org.json.JSONObject

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

    /** Top-level values only, JSON null as null. */
    private fun JSONObject.toMap(): Map<String, Any?> =
        keys().asSequence().associateWith { key -> opt(key).takeUnless { it == JSONObject.NULL } }

    private fun outerRing(geometry: JSONObject): JSONArray? = when (geometry.optString("type")) {
        "Polygon" -> geometry.getJSONArray("coordinates").getJSONArray(0)
        "MultiPolygon" -> geometry.getJSONArray("coordinates").getJSONArray(0).getJSONArray(0)
        else -> null
    }

}
