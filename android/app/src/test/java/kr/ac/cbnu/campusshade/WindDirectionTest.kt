package kr.ac.cbnu.campusshade

import org.junit.Assert.assertEquals
import org.junit.Test

class WindDirectionTest {
    @Test fun sixteenPoints() {
        assertEquals("북", WindDirection.name(0.0))
        assertEquals("북", WindDirection.name(11.2))
        assertEquals("북북동", WindDirection.name(11.25))
        assertEquals("북동", WindDirection.name(45.0))
        assertEquals("동", WindDirection.name(90.0))
        assertEquals("남동", WindDirection.name(135.0))
        assertEquals("남", WindDirection.name(180.0))
        assertEquals("남서", WindDirection.name(225.0))
        assertEquals("서", WindDirection.name(270.0))
        assertEquals("서북서", WindDirection.name(290.0))
        assertEquals("북서", WindDirection.name(315.0))
        assertEquals("북북서", WindDirection.name(337.5))
        assertEquals("북", WindDirection.name(350.0))
        assertEquals("북", WindDirection.name(360.0))
        assertEquals("서", WindDirection.name(-90.0))
    }
}
