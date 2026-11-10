"""UTCI from geometry fields and weather (services/comfort.py), on stand-in geometry."""

import numpy as np
import pytest

from app.services.comfort import comfort_fields
from app.services.solar import SolarPosition
from fakes import fixed_weather, sunny_geometry

SUN = SolarPosition(altitude=60, azimuth=200)
NIGHT = SolarPosition(altitude=-10, azimuth=330)


def test_shade_feels_cooler_than_sun_on_a_hot_afternoon() -> None:
    weather = fixed_weather()
    sun = comfort_fields(sunny_geometry(), weather.when, SUN, weather, weather.wind_ms)
    shade = comfort_fields(sunny_geometry(sunlit=0.0), weather.when, SUN, weather, weather.wind_ms)
    assert np.all(shade.mrt < sun.mrt)
    assert np.all(shade.utci < sun.utci - 3)
    assert sun.irradiance.direct_normal > 0


def test_night_has_no_sun_and_the_mrt_sits_below_the_air() -> None:
    weather = fixed_weather(global_horizontal=0.0, air_temp_c=25.0)
    fields = comfort_fields(sunny_geometry(sunlit=0.0), weather.when, NIGHT, weather, weather.wind_ms)
    assert fields.irradiance.direct_normal == 0
    assert np.all(fields.mrt < 25.0)


def test_more_wind_feels_cooler_and_wind_can_vary_by_cell() -> None:
    weather = fixed_weather()
    geometry = sunny_geometry()
    calm = comfort_fields(geometry, weather.when, SUN, weather, 0.5)
    windy = comfort_fields(geometry, weather.when, SUN, weather, 4.0)
    assert np.all(windy.utci < calm.utci)
    per_cell = np.where(np.arange(geometry.valid.shape[1]) < geometry.valid.shape[1] // 2, 0.5, 4.0)
    mixed = comfort_fields(geometry, weather.when, SUN, weather, np.broadcast_to(per_cell, geometry.valid.shape))
    assert mixed.utci[0, 0] == pytest.approx(calm.utci[0, 0])
    assert mixed.utci[0, -1] == pytest.approx(windy.utci[0, -1])


def test_cells_that_are_not_valid_have_no_value_and_do_not_count() -> None:
    weather = fixed_weather()
    geometry = sunny_geometry()
    geometry.valid[:5] = False
    fields = comfort_fields(geometry, weather.when, SUN, weather, weather.wind_ms)
    assert np.isnan(fields.utci[:5]).all() and np.isfinite(fields.utci[5:]).all()
