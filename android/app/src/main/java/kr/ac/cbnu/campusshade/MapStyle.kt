package kr.ac.cbnu.campusshade

import android.graphics.Color

object MapStyle {
    const val BASE_STYLE_URL = "https://tiles.openfreemap.org/styles/bright"
    const val BUILDING_SOURCE = "campus-buildings"
    const val BUILDING_LAYER = "campus-buildings-extrusion"
    const val SHADOW_SOURCE = "campus-shadows"
    const val SHADOW_LAYER = "campus-shadows-fill"

    val buildingFillColor: Int = Color.rgb(214, 137, 60)
    // 높이 정보가 없어 그림자를 계산하지 않는 건물
    val unknownHeightFillColor: Int = Color.rgb(176, 176, 176)
    val shadowFillColor: Int = Color.rgb(51, 65, 85)
    const val BUILDING_OPACITY = 0.9f
    const val UNKNOWN_HEIGHT_M = 3f
    const val SHADOW_OPACITY = 0.58f

    const val TILT_3D = 55.0
}
