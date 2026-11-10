package kr.ac.cbnu.campusshade.map

import kr.ac.cbnu.campusshade.MapStyle
import kr.ac.cbnu.campusshade.UtciHeatmap
import org.maplibre.android.maps.Style
import org.maplibre.android.style.layers.Property
import org.maplibre.android.style.layers.PropertyFactory.rasterOpacity
import org.maplibre.android.style.layers.PropertyFactory.rasterResampling
import org.maplibre.android.style.layers.RasterLayer
import org.maplibre.android.style.sources.ImageSource

/**
 * The felt-temperature (UTCI) image, one pixel per grid cell. It is added on
 * the first response, under the shadows (which it replaces) and over the
 * satellite photos.
 */
class HeatmapLayer(private val style: Style) {
    /** Draws [heatmap]; true when this added the layer, which then still needs its visibility and opacity. */
    fun show(heatmap: UtciHeatmap): Boolean {
        val source = style.getSourceAs<ImageSource>(MapStyle.HEATMAP_SOURCE)
        if (source == null) {
            style.addSource(ImageSource(MapStyle.HEATMAP_SOURCE, heatmap.quad, heatmap.bitmap))
            style.addLayerBelow(
                RasterLayer(MapStyle.HEATMAP_LAYER, MapStyle.HEATMAP_SOURCE).withProperties(
                    rasterOpacity(MapStyle.HEATMAP_OPACITY),
                    rasterResampling(Property.RASTER_RESAMPLING_LINEAR),
                ),
                MapStyle.SHADOW_LAYER,
            )
            return true
        }
        source.setCoordinates(heatmap.quad)
        source.setImage(heatmap.bitmap)
        return false
    }

    fun setVisible(visible: Boolean) {
        style.getLayer(MapStyle.HEATMAP_LAYER)?.setProperties(visibleIf(visible))
    }
}
