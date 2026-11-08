package kr.ac.cbnu.campusshade

import kotlin.math.floor

object WindDirection {
    private val NAMES = listOf(
        "북", "북북동", "북동", "동북동", "동", "동남동", "남동", "남남동",
        "남", "남남서", "남서", "서남서", "서", "서북서", "북서", "북북서",
    )

    /** 16-point Korean name of the direction [degrees] (0 = north, clockwise). */
    fun name(degrees: Double): String {
        val normalized = ((degrees % 360) + 360) % 360
        return NAMES[floor((normalized + 11.25) / 22.5).toInt() % 16]
    }
}
