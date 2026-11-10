package kr.ac.cbnu.campusshade.map

import kr.ac.cbnu.campusshade.MapStyle
import org.maplibre.android.maps.Style
import org.maplibre.android.style.layers.FillLayer
import org.maplibre.android.style.layers.PropertyFactory.fillColor
import org.maplibre.android.style.layers.PropertyFactory.fillOpacity
import org.maplibre.android.style.sources.GeoJsonSource

/** Building shadow polygons (/api/shadows) under the buildings and the labels. */
class ShadowLayer(private val style: Style) {
    init {
        style.addSource(GeoJsonSource(MapStyle.SHADOW_SOURCE, EMPTY_FEATURE_COLLECTION))
        style.addBelowLabels(
            FillLayer(MapStyle.SHADOW_LAYER, MapStyle.SHADOW_SOURCE).withProperties(
                fillColor(MapStyle.shadowFillColor),
                fillOpacity(MapStyle.SHADOW_OPACITY),
            )
        )
    }

    fun show(geoJson: String) {
        style.getSourceAs<GeoJsonSource>(MapStyle.SHADOW_SOURCE)?.setGeoJson(geoJson)
    }

    fun setVisible(visible: Boolean) {
        style.getLayer(MapStyle.SHADOW_LAYER)?.setProperties(visibleIf(visible))
    }
}
