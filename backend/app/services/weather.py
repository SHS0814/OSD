"""Hourly 청주 ASOS observations, looked up at an arbitrary instant.

The store holds the committed snapshot (scripts/fetch_kma_asos.py).

State variables (air temperature, humidity, wind, cloud) are observed on the
hour and interpolated linearly in between. Solar radiation is different:
``icsr`` is the energy accumulated over the hour *ending* at its timestamp, so
it is turned into a clearness index for that hour and then scaled by where the
sun is at the requested instant. That keeps the sky as cloudy as observed
while letting irradiance follow the sun within the hour.
"""

from __future__ import annotations

import csv
from bisect import bisect_left
from datetime import datetime, timedelta
from pathlib import Path

from .contracts import WeatherSample
from .solar import SEOUL_TZ, calculate_solar_position, localize_datetime
from .thermal import extraterrestrial_horizontal

HOUR = timedelta(hours=1)

Row = dict[str, float | None]


class WeatherUnavailable(LookupError):
    pass


def _number(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class WeatherStore:
    def __init__(self, csv_path: Path, latitude: float, longitude: float):
        self.latitude = latitude
        self.longitude = longitude
        rows: list[tuple[datetime, Row]] = []
        with csv_path.open(encoding="utf-8") as handle:
            for record in csv.DictReader(handle):
                stamp = datetime.strptime(record["tm"], "%Y-%m-%d %H:%M").replace(tzinfo=SEOUL_TZ)
                rows.append((stamp, {key: _number(value) for key, value in record.items() if key != "tm"}))
        self._series: tuple[list[datetime], list[Row]] = ([t for t, _ in rows], [r for _, r in rows])

    @property
    def period(self) -> tuple[datetime, datetime]:
        times = self._series[0]
        return times[0], times[-1]

    def _row(self, stamp: datetime) -> Row | None:
        times, rows = self._series
        index = bisect_left(times, stamp)
        if index < len(times) and times[index] == stamp:
            return rows[index]
        return None

    def _state(self, when: datetime, column: str) -> float:
        before = when.replace(minute=0, second=0, microsecond=0)
        after = before if before == when else before + HOUR
        low_row = self._row(before)
        low_value = low_row.get(column) if low_row else None
        high_row = self._row(after)
        high_value = high_row.get(column) if high_row else None
        if low_value is None and high_value is None:
            raise WeatherUnavailable(f"no {column} observation around {when.isoformat()}")
        if low_value is None or after == before:
            return float(high_value if high_value is not None else low_value)
        if high_value is None:
            return float(low_value)
        weight = (when - before) / HOUR
        return float(low_value + (high_value - low_value) * weight)

    def _clearness(self, hour_end: datetime) -> tuple[float, float]:
        """Clearness index and mean irradiance of the observed hour ending at ``hour_end``."""
        row = self._row(hour_end)
        if row is None:
            raise WeatherUnavailable(f"no radiation observation for the hour ending {hour_end.isoformat()}")
        # A blank icsr is how ASOS reports an hour with no measurable sun.
        mean_global = (row.get("icsr") or 0.0) * 1e6 / 3600.0
        midpoint = hour_end - HOUR / 2
        altitude = calculate_solar_position(midpoint, self.latitude, self.longitude).altitude
        extraterrestrial = extraterrestrial_horizontal(midpoint.timetuple().tm_yday, altitude)
        if extraterrestrial <= 0:
            return 0.0, mean_global
        return min(mean_global / extraterrestrial, 1.0), mean_global

    def at(self, when: datetime) -> WeatherSample:
        when = localize_datetime(when)
        start, latest = self.period
        if when < start or when > latest:
            raise WeatherUnavailable(
                f"weather is available from {start:%Y-%m-%d %H:%M} to {latest:%Y-%m-%d %H:%M} (Asia/Seoul)"
            )

        persisted = False
        state_at = when
        hour_end = when.replace(minute=0, second=0, microsecond=0)
        if hour_end < when:
            hour_end += HOUR
        observed_at = hour_end
        clearness, hour_mean = self._clearness(hour_end)

        altitude = calculate_solar_position(when, self.latitude, self.longitude).altitude
        global_now = clearness * extraterrestrial_horizontal(when.timetuple().tm_yday, altitude)
        wind_ms = self._state(state_at, "ws")
        return WeatherSample(
            when=when,
            observed_at=observed_at,
            persisted=persisted,
            air_temp_c=self._state(state_at, "ta"),
            relative_humidity=self._state(state_at, "hm"),
            dew_point_c=self._state(state_at, "td"),
            vapour_hpa=self._state(state_at, "pv"),
            wind_ms=wind_ms,
            cloud_fraction=min(max(self._state(state_at, "cloud") / 10.0, 0.0), 1.0),
            clearness_index=clearness,
            global_horizontal=max(global_now, 0.0),
            hour_mean_global_horizontal=hour_mean,
        )
