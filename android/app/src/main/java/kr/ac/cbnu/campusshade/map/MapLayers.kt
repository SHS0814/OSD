package kr.ac.cbnu.campusshade.map

import android.content.Context
import org.maplibre.android.maps.Style

/**
 * Every data layer of the map, added in drawing order once the base style is loaded.
 *
 * Satellite photos, shadows and buildings go under the base map's labels; the
 * felt-temperature heatmap is added on its first response, under the shadows
 * and over the photos. Wind arrows sit just over the buildings; routes, their
 * pins and the sensors are drawn over the labels.
 */
class MapLayers(style: Style, context: Context) {
    val satellite = SatelliteLayer(style)
    val shadows = ShadowLayer(style)
    val buildings = BuildingLayer(style)
    val heatmap = HeatmapLayer(style)
    val routes = RouteLayer(style)
    val sensors = SensorLayer(style)
}
