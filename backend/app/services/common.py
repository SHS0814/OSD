"""Small facts both halves of the model rely on (common code: change only by agreement)."""

from __future__ import annotations

from datetime import date

# Ground surface warms above the air in proportion to the sunlight it absorbs.
# Fitted on 청주 ASOS hours with more than 300 W/m² of sun (n = 3,117):
# (ts - ta) / G has median 0.0113 and least-squares slope 0.0129. The land
# cover gives it to grass (surfaces.py); the radiation model takes it as the
# default ground (thermal.py).
GROUND_HEATING_K_PER_W = 0.012


def in_leaf(day: date) -> bool:
    """Broadleaf trees around 청주 leaf out in late April and drop in early November."""
    return date(day.year, 4, 20) <= day <= date(day.year, 11, 10)
