"""Per-cell wind (services/wind.py) on synthetic scenes where the answer is known."""

import math

import numpy as np
import pytest

from app.services.wind import (
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
