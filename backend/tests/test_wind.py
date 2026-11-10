"""Per-cell wind (services/wind.py) on synthetic scenes where the answer is known."""

import math
from datetime import date

import numpy as np
import pytest

from app.services.wind import (
    K_BG,
    STATION_Z0_M,
    WindField,
    background_factor,
    macdonald,
    sector_of,
)
from fakes import cell_of, square_obstacles

SUMMER, WINTER = date(2025, 8, 5), date(2026, 1, 15)

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


def test_open_ground_is_unsheltered() -> None:
    k = WindField(square_obstacles()).shelter_factor(WEST, leaf_on=True)
    assert np.nanmin(k) == pytest.approx(K_BG)
    assert np.nanmax(k) == pytest.approx(K_BG)


def test_a_building_shelters_its_lee_and_the_wake_recovers() -> None:
    # A stand-in raster: one 10 m tall, 20 m wide building; a west wind
    # leaves its wake to the east.
    raster = square_obstacles(buildings=[(0, 0, 10, 10.0)])
    k = WindField(raster).shelter_factor(WEST, leaf_on=True)
    upwind, near, mid, far, beside = (
        k[cell_of(raster, x, y)] for x, y in [(-40, 0), (14, 0), (60, 0), (130, 0), (40, 60)]
    )
    assert upwind == pytest.approx(K_BG)
    assert beside == pytest.approx(K_BG)
    assert near < mid < far < K_BG
    # The cell centre 14 m from the middle lies 4-8 m past the rasterised wall.
    assert K_BG * (1 - 0.7 * np.exp(-4 / 60)) <= near <= K_BG * (1 - 0.7 * np.exp(-8 / 60)) * 1.05
    k_east = WindField(raster).shelter_factor(EAST, leaf_on=True)
    # The same building, wind from the east: the west side is now the lee.
    assert k_east[cell_of(raster, -14, 0)] < 0.5 * K_BG
    assert k_east[cell_of(raster, 14, 0)] == pytest.approx(K_BG)


def test_bare_crowns_shelter_less_than_crowns_in_leaf() -> None:
    raster = square_obstacles(crowns=[(0, 0, 10, 12.0)])
    field = WindField(raster)
    lee = cell_of(raster, 20, 0)
    in_leaf = field.shelter_factor(WEST, leaf_on=True)[lee]
    bare = field.shelter_factor(WEST, leaf_on=False)[lee]
    assert in_leaf < bare < K_BG
    # Own crown at x = 0: deficit 0.7 × (1 − τ), τ = 0.2 in leaf.
    under = cell_of(raster, 0, 0)
    assert field.shelter_factor(WEST, leaf_on=True)[under] == pytest.approx(K_BG * (1 - 0.7 * 0.8), rel=0.02)


def test_wind_ms_scales_asos_speed_and_uses_the_season() -> None:
    raster = square_obstacles(crowns=[(0, 0, 10, 12.0)])
    field = WindField(raster)
    under = cell_of(raster, 0, 0)
    summer = field.wind_ms(3.0, 270, SUMMER)
    winter = field.wind_ms(3.0, 270, WINTER)
    assert summer[under] < winter[under]
    assert np.nanmax(summer[raster.valid]) == pytest.approx(3.0 * K_BG)
    calm = field.wind_ms(0.3, 0, SUMMER)  # calm: mean over the sectors
    assert np.all(np.isfinite(calm))


def test_frontal_area_depends_on_the_wind_direction() -> None:
    # A wall of 8 m squares running east-west, 120 m × 8 m.
    wall = tuple((x, 0.0, 4.0, 10.0) for x in range(-56, 57, 8))
    field = WindField(square_obstacles(buildings=wall))
    assert field.morphometry(NORTH, True)["frontal_index"] > 5 * field.morphometry(EAST, True)["frontal_index"]
