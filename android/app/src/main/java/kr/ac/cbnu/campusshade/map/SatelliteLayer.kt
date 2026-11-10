package kr.ac.cbnu.campusshade.map

import kr.ac.cbnu.campusshade.BuildConfig
import kr.ac.cbnu.campusshade.MapStyle
import org.maplibre.android.maps.Style
import org.maplibre.android.style.layers.RasterLayer
import org.maplibre.android.style.sources.RasterSource
import org.maplibre.android.style.sources.TileSet

/** VWorld aerial photos through the API, over the base map and under its labels. */
class SatelliteLayer(private val style: Style) {
    init {
        val tiles = TileSet("2.2.0", BuildConfig.API_BASE_URL + "api/tiles/satellite/{z}/{x}/{y}.jpeg").apply {
            minZoom = MapStyle.SATELLITE_MIN_ZOOM
            maxZoom = MapStyle.SATELLITE_MAX_ZOOM
        }
        style.addSource(RasterSource(MapStyle.SATELLITE_SOURCE, tiles, 256))
        style.addBelowLabels(RasterLayer(MapStyle.SATELLITE_LAYER, MapStyle.SATELLITE_SOURCE))
    }

    fun setVisible(visible: Boolean) {
        style.getLayer(MapStyle.SATELLITE_LAYER)?.setProperties(visibleIf(visible))
    }
}
