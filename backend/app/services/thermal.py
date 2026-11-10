"""Radiation and thermal comfort physics for a standing pedestrian.

Everything here works element-wise on numpy arrays so one call covers the whole
campus grid. The mean radiant temperature follows a simplified two-hemisphere
form of the SOLWEIG model; see docs/04-data-usage-plan.md for the derivation
and the assumptions behind each constant.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .common import GROUND_HEATING_K_PER_W

STEFAN_BOLTZMANN = 5.67e-8  # W/m²K⁴
SOLAR_CONSTANT = 1367.0  # W/m²
KELVIN = 273.15

PERSON_SHORTWAVE_ABSORPTIVITY = 0.70
PERSON_EMISSIVITY = 0.97
GROUND_EMISSIVITY = 0.95
WALL_EMISSIVITY = 0.90
DEFAULT_GROUND_ALBEDO = 0.15

UTCI_MIN_WIND = 0.5
UTCI_MAX_WIND = 17.0


@dataclass(frozen=True)
class Irradiance:
    """Instantaneous irradiance split into its beam and diffuse parts, in W/m²."""

    global_horizontal: float
    direct_normal: float
    diffuse_horizontal: float


def extraterrestrial_horizontal(day_of_year: int, solar_altitude_deg: float) -> float:
    if solar_altitude_deg <= 0:
        return 0.0
    eccentricity = 1 + 0.033 * math.cos(math.radians(360.0 * day_of_year / 365.0))
    return SOLAR_CONSTANT * eccentricity * math.sin(math.radians(solar_altitude_deg))


def erbs_diffuse_fraction(clearness_index: float) -> float:
    kt = clearness_index
    if kt <= 0.22:
        return 1.0 - 0.09 * kt
    if kt <= 0.80:
        return 0.9511 - 0.1604 * kt + 4.388 * kt**2 - 16.638 * kt**3 + 12.336 * kt**4
    return 0.165


def split_irradiance(
    global_horizontal: float, day_of_year: int, solar_altitude_deg: float
) -> Irradiance:
    """Split global horizontal irradiance into direct normal and diffuse (Erbs 1982)."""
    extraterrestrial = extraterrestrial_horizontal(day_of_year, solar_altitude_deg)
    if extraterrestrial <= 0 or global_horizontal <= 0:
        return Irradiance(0.0, 0.0, 0.0)
    clearness = min(global_horizontal / extraterrestrial, 1.0)
    diffuse = erbs_diffuse_fraction(clearness) * global_horizontal
    direct_horizontal = max(global_horizontal - diffuse, 0.0)
    direct_normal = direct_horizontal / math.sin(math.radians(solar_altitude_deg))
    return Irradiance(global_horizontal, direct_normal, diffuse)


def projected_area_factor(solar_altitude_deg: float) -> float:
    """Fraction of a standing person's surface facing the sun's beam."""
    if solar_altitude_deg <= 0:
        return 0.0
    beta = solar_altitude_deg
    return 0.308 * math.cos(math.radians(beta * (0.998 - beta**2 / 50000.0)))


def sky_emissivity(air_temp_c: np.ndarray | float, vapour_hpa: float, cloud_fraction: float):
    """Brutsaert clear-sky emissivity with a cloud correction."""
    clear = 1.24 * (vapour_hpa / (np.asarray(air_temp_c) + KELVIN)) ** (1.0 / 7.0)
    return np.minimum(clear * (1.0 + 0.22 * cloud_fraction**2), 1.0)


def mean_radiant_temperature(
    *,
    air_temp_c: np.ndarray,
    sunlit: np.ndarray,
    sky_view: np.ndarray,
    irradiance: Irradiance,
    solar_altitude_deg: float,
    vapour_hpa: float,
    cloud_fraction: float,
    ground_albedo: np.ndarray | float = DEFAULT_GROUND_ALBEDO,
    ground_heating: np.ndarray | float = GROUND_HEATING_K_PER_W,
) -> np.ndarray:
    """Mean radiant temperature in °C.

    ``sunlit`` is the unshaded fraction of each cell (1 in full sun, 0 in full
    shade) and ``sky_view`` the sky view factor, both in [0, 1].
    """
    air_k = np.asarray(air_temp_c, dtype=float) + KELVIN
    beam_on_ground = irradiance.direct_normal * max(
        math.sin(math.radians(solar_altitude_deg)), 0.0
    )
    ground_shortwave = beam_on_ground * sunlit + irradiance.diffuse_horizontal * sky_view

    shortwave = PERSON_SHORTWAVE_ABSORPTIVITY * (
        projected_area_factor(solar_altitude_deg) * irradiance.direct_normal * sunlit
        + 0.5 * irradiance.diffuse_horizontal * sky_view
        + 0.5 * ground_albedo * ground_shortwave
    )

    # Same form as the ASOS fit above (incident, not absorbed, shortwave), so the
    # fitted coefficient applies unchanged.
    ground_k = air_k + ground_heating * ground_shortwave
    sky = sky_emissivity(air_temp_c, vapour_hpa, cloud_fraction) * STEFAN_BOLTZMANN * air_k**4
    walls = WALL_EMISSIVITY * STEFAN_BOLTZMANN * air_k**4
    longwave_down = sky_view * sky + (1.0 - sky_view) * walls
    longwave_up = GROUND_EMISSIVITY * STEFAN_BOLTZMANN * ground_k**4
    longwave = PERSON_EMISSIVITY * 0.5 * (longwave_down + longwave_up)

    absorbed = shortwave + longwave
    return (absorbed / (PERSON_EMISSIVITY * STEFAN_BOLTZMANN)) ** 0.25 - KELVIN
