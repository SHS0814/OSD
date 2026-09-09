import math

import pytest
from shapely.geometry import box

from app.services.shadow import (
    calculate_shadow_length,
    calculate_shadow_vector,
    create_shadow_polygon,
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


def test_polygon_translation_creates_swept_shadow() -> None:
    building = box(0, 0, 10, 10)
    shadow = create_shadow_polygon(building, 20, 180)
    assert shadow.bounds == pytest.approx((0, 0, 10, 30))
    assert shadow.area == pytest.approx(300)

