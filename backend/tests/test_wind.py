"""Per-cell wind (services/wind.py) on synthetic scenes where the answer is known."""

from datetime import datetime

import numpy as np
import pytest

from shapely.affinity import rotate, scale

from app.services.solar import SEOUL_TZ, SolarPosition
from app.services.weather import WeatherSample
from app.services.wind import (
    K_BG,
    STATION_Z0_M,
    WindField,
    background_factor,
    macdonald,
    sector_of,
)
from test_microclimate import SUMMER, WINTER, cell_at, scene, square

NORTH, EAST, SOUTH, WEST = 0, 4, 8, 12


def test_sectors_follow_the_compass_and_calm_has_none() -> None:
    assert sector_of(360) == NORTH
    assert sector_of(270) == WEST
    assert sector_of(290) == 13  # WNW
    assert sector_of(90) == EAST
    assert sector_of(0, 0.3) is None  # ASOS writes calm as wd = 0
    assert sector_of(270, 0.2) is None
    assert sector_of(None) is None


def test_background_factor_is_one_on_open_ground_and_less_on_rough() -> None:
    assert background_factor(STATION_Z0_M) == pytest.approx(1.0)
    assert 0.75 < K_BG < 0.9
    assert background_factor(1.0) < K_BG


def test_macdonald_gives_more_roughness_for_more_frontal_area() -> None:
    d_low, z0_low = macdonald(0.2, 0.05, 15.0)
    d_high, z0_high = macdonald(0.2, 0.2, 15.0)
    assert d_low == pytest.approx(d_high)  # d depends on λp only
    assert z0_high > z0_low
    assert macdonald(0.0, 0.0, 0.0) == (0.0, STATION_Z0_M)


def test_open_ground_gets_the_background_factor() -> None:
    k = WindField(scene()).factor(WEST, leaf_on=True)
    assert np.nanmin(k) == pytest.approx(K_BG)
    assert np.nanmax(k) == pytest.approx(K_BG)


def test_a_building_shelters_its_lee_and_the_wake_recovers() -> None:
    # 10 m tall, 20 m wide; a west wind leaves its wake to the east.
    model = scene(buildings=[(square(0, 0, 10), 10.0)])
    k = WindField(model).factor(WEST, leaf_on=True)
    upwind = k[cell_at(model, -40, 0)]
    near = k[cell_at(model, 14, 0)]
    mid = k[cell_at(model, 60, 0)]
    far = k[cell_at(model, 130, 0)]
    beside = k[cell_at(model, 40, 60)]
    assert upwind == pytest.approx(K_BG)
    assert beside == pytest.approx(K_BG)
    assert near < mid < far < K_BG
    assert near == pytest.approx(K_BG * (1 - 0.7 * np.exp(-4 / 60)), rel=0.1)
    # The same building, wind from the east: the west side is now the lee.
    k_east = WindField(model).factor(EAST, leaf_on=True)
    # Cell centres do not sit symmetrically about the walls, hence the tolerance.
    assert k_east[cell_at(model, -14, 0)] == pytest.approx(near, rel=0.1)
    assert k_east[cell_at(model, 14, 0)] == pytest.approx(K_BG)


def test_bare_crowns_shelter_less_than_crowns_in_leaf() -> None:
    model = scene(canopies=[square(0, 0, 10)])
    field = WindField(model)
    lee = cell_at(model, 20, 0)
    in_leaf = field.factor(WEST, leaf_on=True)[lee]
    bare = field.factor(WEST, leaf_on=False)[lee]
    assert in_leaf < bare < K_BG
    under = cell_at(model, 0, 0)
    # Own crown at x = 0: deficit 0.7 × (1 − τ), τ = 0.2 in leaf.
    assert field.factor(WEST, leaf_on=True)[under] == pytest.approx(K_BG * (1 - 0.7 * 0.8), rel=0.02)


def test_frontal_area_depends_on_the_wind_direction() -> None:
    # A wall running east-west, then one running south-west to north-east.
    long_wall = scale(square(0, 0, 4), xfact=15, yfact=1)  # 120 m × 8 m, east-west
    ew = WindField(scene(buildings=[(long_wall, 10.0)]))
    assert ew.morphometry(NORTH, True)["frontal_index"] > 5 * ew.morphometry(EAST, True)["frontal_index"]
    diagonal = WindField(scene(buildings=[(rotate(long_wall, 45, origin="centroid"), 10.0)]))
    # Its long side faces north-west / south-east. The raster staircase along a
    # diagonal edge adds frontal area end-on, so the contrast is smaller.
    assert diagonal.morphometry(14, True)["frontal_index"] > 2 * diagonal.morphometry(2, True)["frontal_index"]


def _weather(wind_ms: float) -> WeatherSample:
    when = datetime(2025, 8, 5, 14, tzinfo=SEOUL_TZ)
    return WeatherSample(
        when=when, observed_at=when, persisted=False, air_temp_c=33.0, relative_humidity=50.0,
        dew_point_c=21.4, vapour_hpa=25.0, wind_ms=wind_ms, cloud_fraction=0.1,
        clearness_index=0.7, global_horizontal=800.0, hour_mean_global_horizontal=800.0,
    )


def test_fields_keep_uniform_wind_unless_asked() -> None:
    model = scene(buildings=[(square(0, 0, 10), 15.0)])
    when = datetime(2025, 8, 5, 14, tzinfo=SEOUL_TZ)
    sun = SolarPosition(altitude=60, azimuth=200)
    weather = _weather(4.0)
    uniform = model.fields(when, sun, weather).utci
    # Attaching a field changes nothing until a direction is passed.
    model.wind_field = WindField(model)
    assert np.array_equal(model.fields(when, sun, weather).utci, uniform, equal_nan=True)
    per_cell = model.fields(when, sun, weather, wind_direction_deg=270).utci
    lee, upwind = cell_at(model, 16, 0), cell_at(model, -60, 0)
    # Less wind on a hot afternoon feels hotter, most of all in the lee.
    assert per_cell[upwind] > uniform[upwind]
    assert per_cell[lee] - uniform[lee] > per_cell[upwind] - uniform[upwind]
    model.wind_field = None
    assert np.array_equal(model.fields(when, sun, weather, wind_direction_deg=270).utci, uniform, equal_nan=True)


def test_wind_ms_scales_asos_speed_and_uses_the_season() -> None:
    model = scene(canopies=[square(0, 0, 10)])
    field = WindField(model)
    under = cell_at(model, 0, 0)
    summer = field.wind_ms(3.0, 270, SUMMER)
    winter = field.wind_ms(3.0, 270, WINTER)
    assert summer[under] < winter[under]
    assert np.nanmax(summer[model.valid]) == pytest.approx(3.0 * K_BG)
    calm = field.wind_ms(0.3, 0, SUMMER)  # calm: mean over the sectors
    assert np.all(np.isfinite(calm))
