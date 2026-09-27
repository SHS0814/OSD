"""Hourly 청주 ASOS observations, looked up at an arbitrary instant.

The snapshot is written by scripts/fetch_kma_asos.py. State variables (air
temperature, humidity, wind, cloud) are observed on the hour and interpolated
linearly in between. Solar radiation is different: ``icsr`` is the energy
accumulated over the hour *ending* at its timestamp, so it is turned into a
clearness index for that hour and then scaled by where the sun is at the
requested instant. That keeps the sky as cloudy as observed while letting
irradiance follow the sun within the hour.
"""

from __future__ import annotations

import csv
from bisect import bisect_left
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from .solar import SEOUL_TZ, calculate_solar_position, localize_datetime
from .thermal import extraterrestrial_horizontal

HOUR = timedelta(hours=1)
STATE_COLUMNS = ("ta", "hm", "td", "pv", "ws", "cloud")


class WeatherUnavailable(LookupError):
    pass


@dataclass(frozen=True)
class WeatherSample:
    when: datetime
    air_temp_c: float
    relative_humidity: float
    dew_point_c: float
    vapour_hpa: float
    wind_ms: float
    cloud_fraction: float
    clearness_index: float
    global_horizontal: float  # instantaneous estimate, W/m²
    hour_mean_global_horizontal: float  # as observed over the enclosing hour, W/m²

    def as_dict(self) -> dict:
        return {
            "station": "청주 ASOS (131)",
            "air_temp_c": round(self.air_temp_c, 2),
            "relative_humidity": round(self.relative_humidity, 1),
            "dew_point_c": round(self.dew_point_c, 2),
            "wind_ms": round(self.wind_ms, 2),
            "cloud_fraction": round(self.cloud_fraction, 2),
            "clearness_index": round(self.clearness_index, 3),
            "global_horizontal_wm2": round(self.global_horizontal, 1),
            "hour_mean_global_horizontal_wm2": round(self.hour_mean_global_horizontal, 1),
        }


def _number(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class WeatherStore:
    def __init__(self, csv_path: Path, latitude: float, longitude: float):
        self.latitude = latitude
        self.longitude = longitude
        self.times: list[datetime] = []
        self.rows: list[dict[str, float | None]] = []
        with csv_path.open(encoding="utf-8") as handle:
            for record in csv.DictReader(handle):
                stamp = datetime.strptime(record["tm"], "%Y-%m-%d %H:%M").replace(tzinfo=SEOUL_TZ)
                self.times.append(stamp)
                self.rows.append({key: _number(value) for key, value in record.items() if key != "tm"})

    @property
    def period(self) -> tuple[datetime, datetime]:
        return self.times[0], self.times[-1]

    def _row(self, stamp: datetime) -> dict[str, float | None] | None:
        index = bisect_left(self.times, stamp)
        if index < len(self.times) and self.times[index] == stamp:
            return self.rows[index]
        return None

    def _state(self, when: datetime, column: str) -> float:
        before = when.replace(minute=0, second=0, microsecond=0)
        after = before if before == when else before + HOUR
        low, high = self._row(before), self._row(after)
        low_value = low.get(column) if low else None
        high_value = high.get(column) if high else None
        if low_value is None and high_value is None:
            raise WeatherUnavailable(f"no {column} observation around {when.isoformat()}")
        if low_value is None or after == before:
            return float(high_value if high_value is not None else low_value)
        if high_value is None:
            return float(low_value)
        weight = (when - before) / HOUR
        return float(low_value + (high_value - low_value) * weight)

    def _clearness(self, when: datetime) -> tuple[float, float]:
        """Clearness index and mean irradiance of the observed hour enclosing ``when``."""
        end = when.replace(minute=0, second=0, microsecond=0)
        if end < when:
            end += HOUR
        row = self._row(end)
        if row is None:
            raise WeatherUnavailable(f"no radiation observation for the hour ending {end.isoformat()}")
        # A blank icsr is how ASOS reports an hour with no measurable sun.
        mean_global = (row.get("icsr") or 0.0) * 1e6 / 3600.0
        midpoint = end - HOUR / 2
        altitude = calculate_solar_position(midpoint, self.latitude, self.longitude).altitude
        extraterrestrial = extraterrestrial_horizontal(midpoint.timetuple().tm_yday, altitude)
        if extraterrestrial <= 0:
            return 0.0, mean_global
        return min(mean_global / extraterrestrial, 1.0), mean_global

    def at(self, when: datetime) -> WeatherSample:
        when = localize_datetime(when)
        start, end = self.period
        if not start <= when <= end:
            raise WeatherUnavailable(
                f"weather snapshot covers {start:%Y-%m-%d %H:%M} to {end:%Y-%m-%d %H:%M} (Asia/Seoul)"
            )
        clearness, hour_mean = self._clearness(when)
        altitude = calculate_solar_position(when, self.latitude, self.longitude).altitude
        global_now = clearness * extraterrestrial_horizontal(when.timetuple().tm_yday, altitude)
        return WeatherSample(
            when=when,
            air_temp_c=self._state(when, "ta"),
            relative_humidity=self._state(when, "hm"),
            dew_point_c=self._state(when, "td"),
            vapour_hpa=self._state(when, "pv"),
            wind_ms=self._state(when, "ws"),
            cloud_fraction=min(max(self._state(when, "cloud") / 10.0, 0.0), 1.0),
            clearness_index=clearness,
            global_horizontal=max(global_now, 0.0),
            hour_mean_global_horizontal=hour_mean,
        )
