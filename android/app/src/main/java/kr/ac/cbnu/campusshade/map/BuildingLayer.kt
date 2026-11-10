package kr.ac.cbnu.campusshade.map

import android.graphics.PointF
import kr.ac.cbnu.campusshade.Building
import kr.ac.cbnu.campusshade.BuildingSearch
import kr.ac.cbnu.campusshade.MapStyle
import org.maplibre.android.maps.MapLibreMap
import org.maplibre.android.maps.Style
import org.maplibre.android.style.expressions.Expression.coalesce
import org.maplibre.android.style.expressions.Expression.color
import org.maplibre.android.style.expressions.Expression.eq
import org.maplibre.android.style.expressions.Expression.get
import org.maplibre.android.style.expressions.Expression.literal
import org.maplibre.android.style.expressions.Expression.switchCase
import org.maplibre.android.style.expressions.Expression.typeOf
import org.maplibre.android.style.layers.FillExtrusionLayer
import org.maplibre.android.style.layers.PropertyFactory.fillExtrusionBase
import org.maplibre.android.style.layers.PropertyFactory.fillExtrusionColor
import org.maplibre.android.style.layers.PropertyFactory.fillExtrusionHeight
import org.maplibre.android.style.layers.PropertyFactory.fillExtrusionOpacity
import org.maplibre.android.style.sources.GeoJsonSource

/** Campus buildings (/api/buildings) extruded to their height; grey where it is unknown. */
class BuildingLayer(private val style: Style) {
    init {
        val hasHeight = eq(typeOf(get("height_m")), literal("number"))
        style.addSource(GeoJsonSource(MapStyle.BUILDING_SOURCE, EMPTY_FEATURE_COLLECTION))
        style.addBelowLabels(
            FillExtrusionLayer(MapStyle.BUILDING_LAYER, MapStyle.BUILDING_SOURCE).withProperties(
                fillExtrusionHeight(coalesce(get("height_m"), literal(MapStyle.UNKNOWN_HEIGHT_M))),
                fillExtrusionBase(0f),
                fillExtrusionColor(
                    switchCase(
                        hasHeight, color(MapStyle.buildingFillColor),
                        color(MapStyle.unknownHeightFillColor),
                    )
                ),
                fillExtrusionOpacity(MapStyle.BUILDING_OPACITY),
            )
        )
    }

    fun show(geoJson: String) {
        style.getSourceAs<GeoJsonSource>(MapStyle.BUILDING_SOURCE)?.setGeoJson(geoJson)
    }

    /** The building drawn at [screen], matched to [buildings] by id or name. */
    fun buildingAt(map: MapLibreMap, screen: PointF, buildings: List<Building>): Building? =
        map.queryRenderedFeatures(screen, MapStyle.BUILDING_LAYER).asSequence()
            .mapNotNull { feature ->
                val id = (if (feature.hasProperty("id")) feature.getNumberProperty("id") else null)?.toLong()
                    ?: feature.id()?.toDoubleOrNull()?.toLong()
                val name = if (feature.hasProperty("name")) feature.getStringProperty("name") else null
                BuildingSearch.findTapped(buildings, id, name)
            }
            .firstOrNull()
}
