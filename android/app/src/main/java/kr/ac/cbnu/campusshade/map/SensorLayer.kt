package kr.ac.cbnu.campusshade.map

import android.graphics.Color
import android.graphics.PointF
import android.graphics.RectF
import kr.ac.cbnu.campusshade.MapStyle
import kr.ac.cbnu.campusshade.SensorInfo
import kr.ac.cbnu.campusshade.SensorSite
import org.maplibre.android.maps.MapLibreMap
import org.maplibre.android.maps.Style
import org.maplibre.android.style.expressions.Expression.get
import org.maplibre.android.style.layers.CircleLayer
import org.maplibre.android.style.layers.Property
import org.maplibre.android.style.layers.PropertyFactory.circleColor
import org.maplibre.android.style.layers.PropertyFactory.circlePitchAlignment
import org.maplibre.android.style.layers.PropertyFactory.circleRadius
import org.maplibre.android.style.layers.PropertyFactory.circleStrokeColor
import org.maplibre.android.style.layers.PropertyFactory.circleStrokeWidth
import org.maplibre.android.style.layers.PropertyFactory.textAnchor
import org.maplibre.android.style.layers.PropertyFactory.textColor
import org.maplibre.android.style.layers.PropertyFactory.textField
import org.maplibre.android.style.layers.PropertyFactory.textFont
import org.maplibre.android.style.layers.PropertyFactory.textHaloColor
import org.maplibre.android.style.layers.PropertyFactory.textHaloWidth
import org.maplibre.android.style.layers.PropertyFactory.textOffset
import org.maplibre.android.style.layers.PropertyFactory.textSize
import org.maplibre.android.style.layers.SymbolLayer
import org.maplibre.android.style.sources.GeoJsonSource

/** Campus sensor sites (/api/sensors) over every other layer and label, so nothing hides them. */
class SensorLayer(private val style: Style) {
    init {
        style.addSource(GeoJsonSource(MapStyle.SENSOR_SOURCE, EMPTY_FEATURE_COLLECTION))
        style.addLayer(
            CircleLayer(MapStyle.SENSOR_LAYER, MapStyle.SENSOR_SOURCE).withProperties(
                circleRadius(MapStyle.SENSOR_RADIUS),
                circleColor(MapStyle.sensorColor),
                circleStrokeColor(Color.WHITE),
                circleStrokeWidth(MapStyle.SENSOR_STROKE_WIDTH),
                circlePitchAlignment(Property.CIRCLE_PITCH_ALIGNMENT_MAP),
            )
        )
        style.addLayer(
            SymbolLayer(MapStyle.SENSOR_LABEL_LAYER, MapStyle.SENSOR_SOURCE).withProperties(
                textField(get("sensor")),
                textFont(MapStyle.labelFont),
                textSize(12f),
                textColor(MapStyle.sensorColor),
                textHaloColor(Color.WHITE),
                textHaloWidth(1.5f),
                textAnchor(Property.TEXT_ANCHOR_TOP),
                textOffset(arrayOf(0f, 0.9f)),
            )
        )
    }

    fun show(geoJson: String) {
        style.getSourceAs<GeoJsonSource>(MapStyle.SENSOR_SOURCE)?.setGeoJson(geoJson)
    }

    fun setVisible(visible: Boolean) {
        val visibility = visibleIf(visible)
        style.getLayer(MapStyle.SENSOR_LAYER)?.setProperties(visibility)
        style.getLayer(MapStyle.SENSOR_LABEL_LAYER)?.setProperties(visibility)
    }

    /** The sensor within [slop] px of [screen] (the dots are small, so a finger's width), if any. */
    fun sensorAt(map: MapLibreMap, screen: PointF, slop: Float, sensors: List<SensorSite>): SensorSite? {
        val box = RectF(screen.x - slop, screen.y - slop, screen.x + slop, screen.y + slop)
        return map.queryRenderedFeatures(box, MapStyle.SENSOR_LAYER).asSequence()
            .mapNotNull { SensorInfo.find(sensors, it.id(), it.getStringProperty("sensor")) }
            .firstOrNull()
    }
}
