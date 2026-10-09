package kr.ac.cbnu.campusshade

import android.graphics.Color

object MapStyle {
    const val BASE_STYLE_URL = "https://tiles.openfreemap.org/styles/bright"
    const val BUILDING_SOURCE = "campus-buildings"
    const val BUILDING_LAYER = "campus-buildings-extrusion"
    const val SHADOW_SOURCE = "campus-shadows"
    const val SHADOW_LAYER = "campus-shadows-fill"
    const val HEATMAP_SOURCE = "campus-utci"
    const val HEATMAP_LAYER = "campus-utci-raster"
    const val SATELLITE_SOURCE = "vworld-satellite"
    const val SATELLITE_LAYER = "vworld-satellite-raster"
    // 서버가 캠퍼스 주변의 이 범위만 VWorld에서 받아 준다 (vworld_tiles.py).
    const val SATELLITE_MIN_ZOOM = 10f
    const val SATELLITE_MAX_ZOOM = 19f
    const val ROUTE_SOURCE = "walk-routes"
    const val ROUTE_CASING_LAYER = "walk-routes-casing"
    const val ROUTE_LAYER = "walk-routes-line"
    const val ROUTE_POINT_SOURCE = "walk-route-ends"
    const val ROUTE_POINT_LAYER = "walk-route-ends-circle"
    // 최단은 회색, 균형은 보라, 그늘은 청록: 히트맵의 초록~빨강과 겹치지 않는 색
    val routeShortestColor: Int = Color.rgb(55, 65, 81)
    val routeBalancedColor: Int = Color.rgb(168, 85, 247)
    val routeCoolestColor: Int = Color.rgb(6, 182, 212)
    val routeStartColor: Int = Color.rgb(22, 163, 74)
    val routeEndColor: Int = Color.rgb(220, 38, 38)
    const val SENSOR_SOURCE = "campus-sensors"
    const val SENSOR_LAYER = "campus-sensors-circle"
    const val SENSOR_LABEL_LAYER = "campus-sensors-label"

    val buildingFillColor: Int = Color.rgb(214, 137, 60)
    // 높이 정보가 없어 그림자를 계산하지 않는 건물
    val unknownHeightFillColor: Int = Color.rgb(176, 176, 176)
    val shadowFillColor: Int = Color.rgb(51, 65, 85)
    const val BUILDING_OPACITY = 0.9f
    const val UNKNOWN_HEIGHT_M = 3f
    const val SHADOW_OPACITY = 0.58f
    const val HEATMAP_OPACITY = 0.78f
    // 위성사진 위에서는 나무·지붕이 비쳐 보이도록 더 투명하게
    const val HEATMAP_OPACITY_ON_SATELLITE = 0.6f

    // 환경 센서 위치: 히트맵의 따뜻한 색과 겹치지 않는 남색 점
    val sensorColor: Int = Color.rgb(37, 99, 235)
    const val SENSOR_RADIUS = 7f
    const val SENSOR_STROKE_WIDTH = 2f
    // 기본 지도(openfreemap bright)에 있는 글꼴이어야 라벨이 그려진다.
    val labelFont = arrayOf("Noto Sans Bold")

    const val TILT_3D = 55.0
}
