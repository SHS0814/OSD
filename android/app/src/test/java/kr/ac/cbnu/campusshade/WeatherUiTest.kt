package kr.ac.cbnu.campusshade

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class WeatherUiTest {
    @Test fun skyFromCloudFraction() {
        assertEquals(Sky.CLEAR, Sky.fromCloudFraction(0.0))
        assertEquals(Sky.CLEAR, Sky.fromCloudFraction(0.5))
        assertEquals(Sky.PARTLY_CLOUDY, Sky.fromCloudFraction(0.6))
        assertEquals(Sky.PARTLY_CLOUDY, Sky.fromCloudFraction(0.8))
        assertEquals(Sky.OVERCAST, Sky.fromCloudFraction(0.9))
        assertEquals(Sky.OVERCAST, Sky.fromCloudFraction(1.0))
        assertNull(Sky.fromCloudFraction(Double.NaN))
    }

    @Test fun moonOnlyAtNight() {
        assertEquals(WeatherIcon.SUN, WeatherIcon.of(Sky.CLEAR, 35.2))
        assertEquals(WeatherIcon.MOON, WeatherIcon.of(Sky.CLEAR, -5.0))
        assertEquals(WeatherIcon.MOON, WeatherIcon.of(Sky.CLEAR, 0.0))
        assertEquals(WeatherIcon.CLOUD, WeatherIcon.of(Sky.OVERCAST, -5.0))
        assertEquals(WeatherIcon.PARTLY_CLOUDY_DAY, WeatherIcon.of(Sky.PARTLY_CLOUDY, 10.0))
        assertEquals(WeatherIcon.PARTLY_CLOUDY_NIGHT, WeatherIcon.of(Sky.PARTLY_CLOUDY, -1.0))
        assertEquals(WeatherIcon.SUN, WeatherIcon.of(null, Double.NaN))
    }
}
