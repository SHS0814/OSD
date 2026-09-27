from datetime import datetime

import pytest

from app.config import settings
from app.services.solar import SEOUL_TZ
from app.services.weather import WeatherStore, WeatherUnavailable


@pytest.fixture(scope="module")
def store() -> WeatherStore:
    return WeatherStore(settings.weather_data_path, settings.campus_latitude, settings.campus_longitude)


def at(store: WeatherStore, text: str):
    return store.at(datetime.fromisoformat(text).replace(tzinfo=SEOUL_TZ))


def test_on_the_hour_matches_the_observation(store: WeatherStore) -> None:
    sample = at(store, "2025-08-05T12:00")
    assert sample.air_temp_c == 31.8
    assert sample.relative_humidity == 57
    # icsr 3.26 MJ/m² over 11:00-12:00
    assert sample.hour_mean_global_horizontal == pytest.approx(3.26e6 / 3600)


def test_state_is_interpolated_between_hours(store: WeatherStore) -> None:
    sample = at(store, "2025-08-05T12:30")
    assert sample.air_temp_c == pytest.approx((31.8 + 32.2) / 2)


def test_radiation_follows_the_sun_within_an_hour(store: WeatherStore) -> None:
    morning = at(store, "2025-08-05T06:10")
    later = at(store, "2025-08-05T06:50")
    assert later.global_horizontal > morning.global_horizontal
    assert morning.clearness_index == later.clearness_index


def test_night_has_no_radiation(store: WeatherStore) -> None:
    assert at(store, "2025-08-05T23:30").global_horizontal == 0


def test_outside_snapshot_raises(store: WeatherStore) -> None:
    with pytest.raises(WeatherUnavailable):
        at(store, "2024-01-01T12:00")
