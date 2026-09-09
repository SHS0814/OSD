package kr.ac.cbnu.campusshade

import android.graphics.Color

object MapStyle {
    const val BASE_STYLE_URL = "https://tiles.openfreemap.org/styles/bright"
    const val BUILDING_SOURCE = "campus-buildings"
    const val BUILDING_LAYER = "campus-buildings-fill"
    const val BUILDING_OUTLINE_LAYER = "campus-buildings-outline"
    const val SHADOW_SOURCE = "campus-shadows"
    const val SHADOW_LAYER = "campus-shadows-fill"

    val buildingFillColor: Int = Color.rgb(214, 137, 60)
    val buildingStrokeColor: Int = Color.rgb(107, 63, 24)
    val shadowFillColor: Int = Color.rgb(51, 65, 85)
    const val BUILDING_OPACITY = 0.76f
    const val SHADOW_OPACITY = 0.58f
}

