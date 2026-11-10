import numpy as np
import pytest

from app.services.thermal import (
    erbs_diffuse_fraction,
    split_irradiance,
)

# A clear August noon in 청주 as ASOS reported it (2025-08-05 12:00).
NOON_ALTITUDE = 69.0
NOON_DAY = 217


def test_diffuse_fraction_is_continuous_and_bounded() -> None:
    for kt in np.linspace(0, 1, 101):
        assert 0.1 < erbs_diffuse_fraction(kt) <= 1.0
    assert erbs_diffuse_fraction(0.22) == pytest.approx(erbs_diffuse_fraction(0.2201), abs=0.01)
    assert erbs_diffuse_fraction(0.80) == pytest.approx(erbs_diffuse_fraction(0.8001), abs=0.01)


def test_irradiance_split_conserves_global_radiation() -> None:
    irradiance = split_irradiance(928.0, NOON_DAY, NOON_ALTITUDE)
    beam_on_ground = irradiance.direct_normal * np.sin(np.radians(NOON_ALTITUDE))
    assert beam_on_ground + irradiance.diffuse_horizontal == pytest.approx(928.0)
    assert irradiance.direct_normal > irradiance.diffuse_horizontal


def test_no_irradiance_at_night() -> None:
    irradiance = split_irradiance(0.0, NOON_DAY, -10.0)
    assert (irradiance.direct_normal, irradiance.diffuse_horizontal) == (0.0, 0.0)
