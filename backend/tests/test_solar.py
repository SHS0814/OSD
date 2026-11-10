from datetime import datetime
from zoneinfo import ZoneInfo

from app.services.solar import calculate_solar_position


SEOUL = ZoneInfo("Asia/Seoul")


def test_noon_sun_is_above_horizon_and_southward() -> None:
    result = calculate_solar_position(
        datetime(2026, 9, 9, 12, 30, tzinfo=SEOUL), 36.6268, 127.4583
    )
    assert result.altitude > 45
    assert 150 < result.azimuth < 210


def test_night_sun_is_below_horizon() -> None:
    result = calculate_solar_position(
        datetime(2026, 9, 9, 2, 0, tzinfo=SEOUL), 36.6268, 127.4583
    )
    assert result.altitude <= 0

