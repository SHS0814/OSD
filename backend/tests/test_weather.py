from datetime import datetime, timedelta

import pytest

from app.config import settings
from app.services.solar import SEOUL_TZ
from app.services.weather import (
    HOUR,
    PERSISTENCE_LIMIT,
    WeatherStore,
    WeatherUnavailable,
    clearness_from_cloud,
)


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


def fresh_store() -> WeatherStore:
    return WeatherStore(settings.weather_data_path, settings.campus_latitude, settings.campus_longitude)


def test_extend_appends_new_hours() -> None:
    store = fresh_store()
    latest = store.latest
    row = {"ta": 20.0, "hm": 70.0, "td": 14.4, "pv": 16.4, "ws": 1.0, "wd": 90.0,
           "icsr": 1.5, "ss": 0.5, "cloud": 5.0, "ts": 22.0}
    assert store.extend([(latest + HOUR, row), (latest, store._row(latest))]) == 1
    assert store.latest == latest + HOUR
    assert store.at(latest + HOUR).air_temp_c == 20.0


def test_latest_observation_is_carried_forward() -> None:
    store = fresh_store()
    latest = store.latest
    sample = store.at(latest + timedelta(minutes=40))
    assert sample.persisted
    assert sample.observed_at == latest
    assert sample.air_temp_c == store.at(latest).air_temp_c
    with pytest.raises(WeatherUnavailable):
        store.at(latest + PERSISTENCE_LIMIT + HOUR)


def test_clearness_from_cloud_is_lower_under_overcast() -> None:
    assert clearness_from_cloud(0.0) > clearness_from_cloud(0.5) > clearness_from_cloud(1.0) > 0


def test_a_missing_value_in_the_latest_hour_falls_back_to_the_hour_before() -> None:
    store = fresh_store()
    latest = store.latest
    previous_cloud = store._row(latest)["cloud"]
    gap = dict(store._row(latest), cloud=None)
    store.extend([(latest + HOUR, gap)])
    sample = store.at(latest + HOUR + timedelta(minutes=20))
    assert sample.persisted
    assert sample.cloud_fraction == pytest.approx(previous_cloud / 10)
