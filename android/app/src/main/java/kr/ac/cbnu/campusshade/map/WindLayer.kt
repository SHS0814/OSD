package kr.ac.cbnu.campusshade.map

import android.content.Context
import androidx.core.content.ContextCompat
import androidx.core.graphics.drawable.toBitmap
import kr.ac.cbnu.campusshade.MapStyle
import kr.ac.cbnu.campusshade.R
import org.maplibre.android.maps.Style
import org.maplibre.android.style.expressions.Expression.get
import org.maplibre.android.style.expressions.Expression.interpolate
import org.maplibre.android.style.expressions.Expression.linear
import org.maplibre.android.style.expressions.Expression.literal
import org.maplibre.android.style.expressions.Expression.stop
import org.maplibre.android.style.expressions.Expression.sum
import org.maplibre.android.style.layers.Property
import org.maplibre.android.style.layers.PropertyFactory.iconAllowOverlap
import org.maplibre.android.style.layers.PropertyFactory.iconIgnorePlacement
import org.maplibre.android.style.layers.PropertyFactory.iconImage
import org.maplibre.android.style.layers.PropertyFactory.iconOpacity
import org.maplibre.android.style.layers.PropertyFactory.iconPitchAlignment
import org.maplibre.android.style.layers.PropertyFactory.iconRotate
import org.maplibre.android.style.layers.PropertyFactory.iconRotationAlignment
import org.maplibre.android.style.layers.PropertyFactory.iconSize
import org.maplibre.android.style.layers.SymbolLayer
import org.maplibre.android.style.sources.GeoJsonSource

/** Per-cell wind arrows (/api/wind), just over the buildings and under the labels. */
class WindLayer(private val style: Style, context: Context) {
    init {
        ContextCompat.getDrawable(context, R.drawable.ic_wind_arrow)?.let {
            style.addImage(MapStyle.WIND_ARROW_IMAGE, it.toBitmap())
        }
        style.addSource(GeoJsonSource(MapStyle.WIND_SOURCE, EMPTY_FEATURE_COLLECTION))
        style.addLayerAbove(
            SymbolLayer(MapStyle.WIND_LAYER, MapStyle.WIND_SOURCE).withProperties(
                iconImage(MapStyle.WIND_ARROW_IMAGE),
                // 불어가는 쪽(direction + 180°)을 가리킨다.
                iconRotate(sum(get("direction_deg"), literal(180))),
                iconRotationAlignment(Property.ICON_ROTATION_ALIGNMENT_MAP),
                iconPitchAlignment(Property.ICON_PITCH_ALIGNMENT_MAP),
                iconAllowOverlap(true),
                iconIgnorePlacement(true),
                // 약한 바람은 작고 흐리게, 센 바람은 크고 진하게
                iconSize(interpolate(linear(), get("speed_ms"), stop(0, 0.45f), stop(2, 0.7f), stop(5, 1.0f), stop(8, 1.3f))),
                iconOpacity(interpolate(linear(), get("speed_ms"), stop(0, 0.35f), stop(2, 0.65f), stop(5, 0.9f), stop(8, 1f))),
            ),
            MapStyle.BUILDING_LAYER,
        )
    }

    fun show(geoJson: String) {
        style.getSourceAs<GeoJsonSource>(MapStyle.WIND_SOURCE)?.setGeoJson(geoJson)
    }

    fun clear() = show(EMPTY_FEATURE_COLLECTION)
}
