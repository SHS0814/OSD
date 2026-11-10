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

    const val TILT_3D = 55.0
}
