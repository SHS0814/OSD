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

STEFAN_BOLTZMANN = 5.67e-8  # W/m²K⁴
SOLAR_CONSTANT = 1367.0  # W/m²
KELVIN = 273.15

PERSON_SHORTWAVE_ABSORPTIVITY = 0.70
PERSON_EMISSIVITY = 0.97
GROUND_EMISSIVITY = 0.95
WALL_EMISSIVITY = 0.90
DEFAULT_GROUND_ALBEDO = 0.15

# Ground surface warms above the air in proportion to the sunlight it absorbs.
# Fitted on 청주 ASOS hours with more than 300 W/m² of sun (n = 3,117):
# (ts - ta) / G has median 0.0113 and least-squares slope 0.0129.
GROUND_HEATING_K_PER_W = 0.012

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
    ground_k = air_k + GROUND_HEATING_K_PER_W * ground_shortwave
    sky = sky_emissivity(air_temp_c, vapour_hpa, cloud_fraction) * STEFAN_BOLTZMANN * air_k**4
    walls = WALL_EMISSIVITY * STEFAN_BOLTZMANN * air_k**4
    longwave_down = sky_view * sky + (1.0 - sky_view) * walls
    longwave_up = GROUND_EMISSIVITY * STEFAN_BOLTZMANN * ground_k**4
    longwave = PERSON_EMISSIVITY * 0.5 * (longwave_down + longwave_up)

    absorbed = shortwave + longwave
    return (absorbed / (PERSON_EMISSIVITY * STEFAN_BOLTZMANN)) ** 0.25 - KELVIN


def relative_humidity(air_temp_c: np.ndarray, dew_point_c: float) -> np.ndarray:
    """Relative humidity in % from the dew point (Magnus formula)."""

    def saturation(temp_c):
        return 6.112 * np.exp(17.62 * temp_c / (243.12 + temp_c))

    return np.clip(100.0 * saturation(dew_point_c) / saturation(np.asarray(air_temp_c)), 0, 100)


def utci(
    air_temp_c: np.ndarray, mrt_c: np.ndarray, wind_ms: np.ndarray | float, rh_percent: np.ndarray
) -> np.ndarray:
    """Universal Thermal Climate Index in °C; NaN where inputs leave its valid range."""
    from pythermalcomfort.models import utci as utci_model

    wind = np.clip(np.broadcast_to(wind_ms, np.shape(air_temp_c)), UTCI_MIN_WIND, UTCI_MAX_WIND)
    result = utci_model(
        tdb=np.asarray(air_temp_c, dtype=float),
        tr=np.asarray(mrt_c, dtype=float),
        v=np.asarray(wind, dtype=float),
        rh=np.asarray(rh_percent, dtype=float),
        limit_inputs=True,
    )
    return np.asarray(result.utci, dtype=float)


UTCI_CATEGORIES = (
    (46.0, "extreme_heat", "극심한 더위"),
    (38.0, "very_strong_heat", "매우 강한 더위"),
    (32.0, "strong_heat", "강한 더위"),
    (26.0, "moderate_heat", "보통 더위"),
    (9.0, "no_stress", "열 스트레스 없음"),
    (0.0, "slight_cold", "약한 추위"),
    (-13.0, "moderate_cold", "보통 추위"),
    (-27.0, "strong_cold", "강한 추위"),
    (-40.0, "very_strong_cold", "매우 강한 추위"),
)


def utci_category(value: float) -> tuple[str, str]:
    for lower, code, label in UTCI_CATEGORIES:
        if value >= lower:
            return code, label
    return "extreme_cold", "극심한 추위"
