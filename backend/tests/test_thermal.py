import numpy as np
import pytest

from app.services.thermal import (
    erbs_diffuse_fraction,
    mean_radiant_temperature,
    projected_area_factor,
    split_irradiance,
)

# A clear August noon in 청주 as ASOS reported it (2025-08-05 12:00).
NOON_ALTITUDE = 69.0
NOON_DAY = 217


def noon_mrt(sunlit: float, sky_view: float) -> float:
    irradiance = split_irradiance(928.0, NOON_DAY, NOON_ALTITUDE)
    return float(
        mean_radiant_temperature(
            air_temp_c=np.array([31.8]),
            sunlit=np.array([sunlit]),
            sky_view=np.array([sky_view]),
            irradiance=irradiance,
            solar_altitude_deg=NOON_ALTITUDE,
            vapour_hpa=26.8,
            cloud_fraction=0.3,
        )[0]
    )


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
    assert projected_area_factor(-10.0) == 0.0


def test_projected_area_shrinks_as_sun_rises() -> None:
    assert projected_area_factor(10.0) > projected_area_factor(45.0) > projected_area_factor(80.0)


def test_shade_lowers_mean_radiant_temperature_by_tens_of_degrees() -> None:
    sun = noon_mrt(sunlit=1.0, sky_view=1.0)
    shade = noon_mrt(sunlit=0.0, sky_view=0.5)
    # Published street measurements put sun-shade Tmrt gaps at roughly 10-30 °C.
    assert 50 < sun < 70
    assert 10 < sun - shade < 35
