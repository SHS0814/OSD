import math

import pytest

from app.services.shadow import (
    calculate_shadow_length,
    calculate_shadow_vector,
)


def test_height_twenty_at_45_degrees_casts_twenty_meters() -> None:
    assert calculate_shadow_length(20, 45) == pytest.approx(20)


def test_non_positive_altitude_has_no_length() -> None:
    assert calculate_shadow_length(20, 0) == 0
    assert calculate_shadow_length(20, -10) == 0


def test_shadow_vector_is_opposite_sun() -> None:
    dx, dy = calculate_shadow_vector(20, 180)
    assert dx == pytest.approx(0, abs=1e-9)
    assert dy == pytest.approx(20)

