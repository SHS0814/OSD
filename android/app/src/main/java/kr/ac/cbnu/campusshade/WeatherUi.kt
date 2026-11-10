package kr.ac.cbnu.campusshade

/** 기상청 하늘상태 from total cloud cover in tenths: 0–5 맑음, 6–8 구름많음, 9–10 흐림. */
enum class Sky {
    CLEAR, PARTLY_CLOUDY, OVERCAST;

    companion object {
        /** [cloudFraction] is cloud cover from 0 to 1; NaN when it was not observed. */
        fun fromCloudFraction(cloudFraction: Double): Sky? = when {
            cloudFraction.isNaN() -> null
            cloudFraction <= 0.5 + 1e-9 -> CLEAR
            cloudFraction <= 0.8 + 1e-9 -> PARTLY_CLOUDY
            else -> OVERCAST
        }
    }
}

enum class WeatherIcon {
    SUN, MOON, PARTLY_CLOUDY_DAY, PARTLY_CLOUDY_NIGHT, CLOUD;

    companion object {
        /** The sun or the moon by [solarAltitude] (degrees), behind clouds by [sky]. */
        fun of(sky: Sky?, solarAltitude: Double): WeatherIcon {
            val night = !solarAltitude.isNaN() && solarAltitude <= 0
            return when (sky) {
                Sky.OVERCAST -> CLOUD
                Sky.PARTLY_CLOUDY -> if (night) PARTLY_CLOUDY_NIGHT else PARTLY_CLOUDY_DAY
                Sky.CLEAR, null -> if (night) MOON else SUN
            }
        }
    }
}
