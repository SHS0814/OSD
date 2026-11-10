"""Felt temperature per cell from the geometry fields and the weather - the comfort half of model v1.

The space side (geometry_field.py) says how much sun, sky and warm ground
each output cell has (``GeometryFields``); this turns that and the 청주
ASOS hour (``WeatherSample``) into the mean radiant temperature and UTCI.
Air temperature and humidity are the same everywhere; the wind is the ASOS
speed or, when given, a per-cell field (wind.py). The sensor correction of
air temperature is v2 (docs/04-data-usage-plan.md).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import numpy as np

from .contracts import GeometryFields, WeatherSample
from .solar import SolarPosition
from .thermal import (
    mean_radiant_temperature,
    relative_humidity,
    split_irradiance,
    utci,
    utci_category,
)


@dataclass(frozen=True)
class Fields:
    irradiance: object  # thermal.Irradiance
    sunlit: np.ndarray
    mrt: np.ndarray
    utci: np.ndarray  # NaN outside campus and under buildings


def comfort_fields(
    geometry: GeometryFields,
    when: datetime,
    solar: SolarPosition,
    weather: WeatherSample,
    wind_ms: np.ndarray | float,
) -> Fields:
    """Tmrt and UTCI of every valid cell for one instant; ``wind_ms`` per cell or one value."""
    irradiance = split_irradiance(
        weather.global_horizontal, when.timetuple().tm_yday, solar.altitude
    )
    air = np.full(geometry.valid.shape, weather.air_temp_c)
    mrt = mean_radiant_temperature(
        air_temp_c=air,
        sunlit=np.nan_to_num(geometry.sunlit),
        sky_view=np.nan_to_num(geometry.sky_view, nan=1.0),
        irradiance=irradiance,
        solar_altitude_deg=solar.altitude,
        vapour_hpa=weather.vapour_hpa,
        cloud_fraction=weather.cloud_fraction,
        ground_albedo=geometry.albedo,
        ground_heating=geometry.heating,
    )
    humidity = relative_humidity(air, weather.dew_point_c)
    comfort = utci(air, mrt, wind_ms, humidity)
    return Fields(
        irradiance=irradiance,
        sunlit=geometry.sunlit,
        mrt=np.where(geometry.valid, mrt, np.nan),
        utci=np.where(geometry.valid, comfort, np.nan),
    )


def summary(fields: Fields, valid: np.ndarray) -> dict:
    """Campus statistics of one instant; cells outside ``valid`` do not count."""
    comfort, mrt, sunlit = fields.utci, fields.mrt, fields.sunlit
    values = comfort[np.isfinite(comfort)]
    categories: dict[str, int] = {}
    for value in values:
        code, _ = utci_category(float(value))
        categories[code] = categories.get(code, 0) + 1
    return {
        "cell_count": int(valid.sum()),
        "utci_min": _round(values.min()) if values.size else None,
        "utci_mean": _round(values.mean()) if values.size else None,
        "utci_max": _round(values.max()) if values.size else None,
        "mrt_mean": _round(np.nanmean(mrt)) if values.size else None,
        "sunlit_share": _round(np.nanmean(sunlit), 3),
        "categories": categories,
    }


def _round(value: float, digits: int = 1) -> float:
    return round(float(value), digits)
