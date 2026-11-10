package kr.ac.cbnu.campusshade.map

import android.graphics.Color
import kr.ac.cbnu.campusshade.MapStyle
import kr.ac.cbnu.campusshade.Place
import kr.ac.cbnu.campusshade.Places
import org.maplibre.android.maps.Style
import org.maplibre.android.style.expressions.Expression.all
import org.maplibre.android.style.expressions.Expression.color
import org.maplibre.android.style.expressions.Expression.eq
import org.maplibre.android.style.expressions.Expression.get
import org.maplibre.android.style.expressions.Expression.literal
import org.maplibre.android.style.expressions.Expression.match
import org.maplibre.android.style.expressions.Expression.stop
import org.maplibre.android.style.expressions.Expression.switchCase
import org.maplibre.android.style.layers.CircleLayer
import org.maplibre.android.style.layers.LineLayer
import org.maplibre.android.style.layers.Property
import org.maplibre.android.style.layers.PropertyFactory.circleColor
import org.maplibre.android.style.layers.PropertyFactory.circleRadius
import org.maplibre.android.style.layers.PropertyFactory.circleStrokeColor
import org.maplibre.android.style.layers.PropertyFactory.circleStrokeWidth
import org.maplibre.android.style.layers.PropertyFactory.lineCap
import org.maplibre.android.style.layers.PropertyFactory.lineColor
import org.maplibre.android.style.layers.PropertyFactory.lineJoin
import org.maplibre.android.style.layers.PropertyFactory.lineWidth
import org.maplibre.android.style.sources.GeoJsonSource

/** Walking routes (/api/route) and their start/end pins, over the labels to stand out. */
class RouteLayer(private val style: Style) {
    init {
        style.addSource(GeoJsonSource(MapStyle.ROUTE_SOURCE, EMPTY_FEATURE_COLLECTION))
        style.addLayer(
            LineLayer(MapStyle.ROUTE_CASING_LAYER, MapStyle.ROUTE_SOURCE).withProperties(
                lineColor(Color.WHITE),
                lineWidth(9f),
                lineCap(Property.LINE_CAP_ROUND),
                lineJoin(Property.LINE_JOIN_ROUND),
            )
        )
        style.addLayer(
            LineLayer(MapStyle.ROUTE_LAYER, MapStyle.ROUTE_SOURCE).withProperties(
                lineColor(
                    // 추울 때(mode=cold)의 coolest는 햇볕길이라 따뜻한 색으로 그린다.
                    switchCase(
                        all(eq(get("mode"), literal("cold")), eq(get("kind"), literal("coolest"))),
                        color(MapStyle.routeSunnyColor),
                        match(
                            get("kind"), color(MapStyle.routeShortestColor),
                            stop("balanced", color(MapStyle.routeBalancedColor)),
                            stop("coolest", color(MapStyle.routeCoolestColor)),
                        ),
                    )
                ),
                lineWidth(5f),
                lineCap(Property.LINE_CAP_ROUND),
                lineJoin(Property.LINE_JOIN_ROUND),
            )
        )
        style.addSource(GeoJsonSource(MapStyle.ROUTE_POINT_SOURCE, EMPTY_FEATURE_COLLECTION))
        style.addLayer(
            CircleLayer(MapStyle.ROUTE_POINT_LAYER, MapStyle.ROUTE_POINT_SOURCE).withProperties(
                circleRadius(8f),
                circleColor(
                    match(get("role"), color(MapStyle.routeEndColor), stop("start", color(MapStyle.routeStartColor)))
                ),
                circleStrokeColor(Color.WHITE),
                circleStrokeWidth(3f),
            )
        )
    }

    /** The routes FeatureCollection, or nothing for null. */
    fun showRoutes(geoJson: String?) {
        style.getSourceAs<GeoJsonSource>(MapStyle.ROUTE_SOURCE)?.setGeoJson(geoJson ?: EMPTY_FEATURE_COLLECTION)
    }

    fun showEnds(start: Place?, end: Place?) {
        style.getSourceAs<GeoJsonSource>(MapStyle.ROUTE_POINT_SOURCE)?.setGeoJson(Places.endpointsGeoJson(start, end))
    }
}
