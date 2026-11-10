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

SOLAR_CONSTANT = 1367.0  # W/m²


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
