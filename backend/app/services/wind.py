"""Per-cell wind for UTCI - compass sectors and calm, in the ASOS convention."""

from __future__ import annotations

import math


SECTORS = 16
SECTOR_DEG = 360.0 / SECTORS
# ASOS reports wd = 0 with ws < 0.5 for calm (north is 360).
CALM_MS = 0.5


def sector_of(direction_deg: float | None, speed_ms: float | None = None) -> int | None:
    """Compass sector 0 (N) .. 15 (NNW) of a 'from' direction; None when calm."""
    if direction_deg is None or not math.isfinite(direction_deg):
        return None
    if direction_deg == 0 or (speed_ms is not None and speed_ms < CALM_MS):
        return None
    return int(round(direction_deg / SECTOR_DEG)) % SECTORS
