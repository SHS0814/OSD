package kr.ac.cbnu.campusshade.map

import android.annotation.SuppressLint
import android.graphics.PointF
import android.view.MotionEvent
import android.view.ViewConfiguration
import kr.ac.cbnu.campusshade.Place
import org.maplibre.android.maps.MapLibreMap
import org.maplibre.android.maps.MapView
import kotlin.math.hypot

/**
 * A touch that starts on a route pin drags the pin instead of the map; any
 * other touch goes to the map as before. MapLibre has no draggable marker, so
 * this sits in front of the map's own gestures.
 */
class PinDragger(
    private val mapView: MapView,
    private val map: MapLibreMap,
    private val pins: Pins,
) {
    /** Where the route pins are, and what to do as one is dragged ("start" or "end"). */
    interface Pins {
        fun place(role: String): Place?
        fun move(role: String, place: Place?)
        fun drop(role: String, screen: PointF)
    }

    // 누른 핀("start"/"end"), 손가락과 핀 중심의 차이, 끌기 전 자리
    private var dragRole: String? = null
    private var dragOffset = PointF()
    private var dragDown = PointF()
    private var dragMoved = false
    private var dragOriginal: Place? = null

    @SuppressLint("ClickableViewAccessibility")
    fun attach() {
        val touchSlop = ViewConfiguration.get(mapView.context).scaledTouchSlop
        mapView.setOnTouchListener { _, event -> onMapTouch(event, touchSlop) }
    }

    private fun onMapTouch(event: MotionEvent, touchSlop: Int): Boolean {
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                val (role, pin) = pinNear(event.x, event.y) ?: return false
                dragRole = role
                dragOffset = PointF(pin.x - event.x, pin.y - event.y)
                dragDown = PointF(event.x, event.y)
                dragMoved = false
                dragOriginal = pins.place(role)
                return true
            }
            MotionEvent.ACTION_MOVE -> {
                val role = dragRole ?: return false
                if (!dragMoved && hypot(event.x - dragDown.x, event.y - dragDown.y) < touchSlop) return true
                dragMoved = true
                val point = map.projection.fromScreenLocation(PointF(event.x + dragOffset.x, event.y + dragOffset.y))
                val place = (dragOriginal ?: return true).copy(point = point)
                pins.move(role, place)
                return true
            }
            MotionEvent.ACTION_UP -> {
                val role = dragRole ?: return false
                dragRole = null
                if (dragMoved) pins.drop(role, PointF(event.x + dragOffset.x, event.y + dragOffset.y))
                return true
            }
            MotionEvent.ACTION_CANCEL -> {
                val role = dragRole ?: return false
                dragRole = null
                pins.move(role, dragOriginal)
                return true
            }
            // 끄는 동안 두 번째 손가락(확대·회전)도 지도에 넘기지 않는다.
            else -> return dragRole != null
        }
    }

    /** The route pin within reach of a touch at [x], [y] and its screen point, nearest first. */
    private fun pinNear(x: Float, y: Float): Pair<String, PointF>? {
        val reach = PIN_TOUCH_DP * mapView.resources.displayMetrics.density
        return listOfNotNull(pins.place("start")?.let { "start" to it }, pins.place("end")?.let { "end" to it })
            .map { (role, place) -> role to map.projection.toScreenLocation(place.point) }
            .map { (role, pin) -> Triple(role, pin, hypot(pin.x - x, pin.y - y)) }
            .filter { it.third <= reach }
            .minByOrNull { it.third }
            ?.let { it.first to it.second }
    }

    private companion object {
        // 출발·도착 핀(반지름 8 + 테두리 3)보다 넉넉히: 이 안에서 누르면 핀을 끈다.
        const val PIN_TOUCH_DP = 28f
    }
}
