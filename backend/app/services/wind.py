"""Per-cell wind for UTCI - compass sectors, calm, and the background factor K_BG.

K_BG brings the 10 m wind at the open ASOS site (z0 ≈ 0.03 m) to the rougher
campus (z0 ≈ 0.5 m, Wieringa 1992) by taking the wind as equal at a blending
height of 60 m and bringing it down with the log law (Wieringa 1986).
``macdonald`` gives the roughness of an array of obstacles for comparison.
"""

from __future__ import annotations

import math


SECTORS = 16
SECTOR_DEG = 360.0 / SECTORS
# ASOS reports wd = 0 with ws < 0.5 for calm (north is 360).
CALM_MS = 0.5

STATION_Z0_M = 0.03  # WMO open-terrain site
CAMPUS_Z0_M = 0.5  # Wieringa (1992) "very rough": scattered buildings and trees
BLENDING_HEIGHT_M = 60.0
REFERENCE_HEIGHT_M = 10.0
# Macdonald et al. (1998) constants for staggered cubes.
MACDONALD_A = 4.43
MACDONALD_BETA = 1.0
DRAG_COEFFICIENT = 1.2
VON_KARMAN = 0.4

K_MIN = 0.05


def sector_of(direction_deg: float | None, speed_ms: float | None = None) -> int | None:
    """Compass sector 0 (N) .. 15 (NNW) of a 'from' direction; None when calm."""
    if direction_deg is None or not math.isfinite(direction_deg):
        return None
    if direction_deg == 0 or (speed_ms is not None and speed_ms < CALM_MS):
        return None
    return int(round(direction_deg / SECTOR_DEG)) % SECTORS


def macdonald(plan_index: float, frontal_index: float, height_m: float) -> tuple[float, float]:
    """Displacement height d and roughness length z0 (m), Macdonald et al. 1998."""
    if height_m <= 0 or plan_index <= 0:
        return 0.0, STATION_Z0_M
    d_ratio = 1.0 + MACDONALD_A ** (-plan_index) * (plan_index - 1.0)
    exponent = 0.5 * MACDONALD_BETA * DRAG_COEFFICIENT / VON_KARMAN**2 * (1.0 - d_ratio) * frontal_index
    z0_ratio = (1.0 - d_ratio) * math.exp(-exponent ** -0.5) if exponent > 0 else 0.0
    return d_ratio * height_m, max(z0_ratio * height_m, STATION_Z0_M)


def background_factor(z0_m: float = CAMPUS_Z0_M, d_m: float = 0.0) -> float:
    """10 m wind over terrain (z0, d) relative to 10 m wind at the open ASOS site."""
    station = math.log(REFERENCE_HEIGHT_M / STATION_Z0_M) / math.log(BLENDING_HEIGHT_M / STATION_Z0_M)
    above = REFERENCE_HEIGHT_M - d_m
    if above <= z0_m:
        return K_MIN
    campus = math.log(above / z0_m) / math.log((BLENDING_HEIGHT_M - d_m) / z0_m)
    return min(max(campus / station, K_MIN), 1.0)


K_BG = background_factor()
