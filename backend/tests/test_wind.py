"""Per-cell wind (services/wind.py) on synthetic scenes where the answer is known."""

import math

import numpy as np
import pytest

from app.services.wind import (
    K_BG,
    STATION_Z0_M,
    background_factor,
    macdonald,
    sector_of,
)

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
