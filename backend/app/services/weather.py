"""Hourly 청주 ASOS observations, looked up at an arbitrary instant.

The store starts from the committed snapshot (scripts/fetch_kma_asos.py) and,
when an API허브 key is configured, is extended with newer hours as they are
observed (services/kma_hub.py), so "now" can be answered.

State variables (air temperature, humidity, wind, cloud) are observed on the
hour and interpolated linearly in between. Solar radiation is different:
``icsr`` is the energy accumulated over the hour *ending* at its timestamp, so
it is turned into a clearness index for that hour and then scaled by where the
sun is at the requested instant. That keeps the sky as cloudy as observed
while letting irradiance follow the sun within the hour.

For an instant after the latest observation - the current hour is only
reported once it ends - the latest observation is carried forward for up to
PERSISTENCE_LIMIT, and the sample says so.
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
PERSISTENCE_LIMIT = timedelta(hours=3)
MISSING_FILL = timedelta(hours=3)

# Below this much sun above the atmosphere the hour's clearness index is mostly
# noise (the hour straddles sunrise), so it is estimated from cloud cover.
MIN_RELIABLE_EXTRATERRESTRIAL = 100.0  # W/m²

Row = dict[str, float | None]


class WeatherUnavailable(LookupError):
    pass


@dataclass(frozen=True)
class WeatherSample:
    when: datetime
    observed_at: datetime  # latest observation the sample draws on
    persisted: bool  # True when carried forward past the latest observation
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
            "observed_at": self.observed_at.isoformat(),
            "persisted": self.persisted,
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


def clearness_from_cloud(cloud_fraction: float) -> float:
    """Kasten-Czeplak: G = G_clear(1 - 0.75 N^3.4), with G_clear ≈ 0.75 G₀."""
    return 0.75 * (1.0 - 0.75 * cloud_fraction**3.4)


class WeatherStore:
    def __init__(self, csv_path: Path, latitude: float, longitude: float):
        self.latitude = latitude
        self.longitude = longitude
        rows: list[tuple[datetime, Row]] = []
        with csv_path.open(encoding="utf-8") as handle:
            for record in csv.DictReader(handle):
                stamp = datetime.strptime(record["tm"], "%Y-%m-%d %H:%M").replace(tzinfo=SEOUL_TZ)
                rows.append((stamp, {key: _number(value) for key, value in record.items() if key != "tm"}))
        # (times, rows) is replaced as a whole by extend(), so a request reading
        # it from another thread always sees a consistent pair.
        self._series: tuple[list[datetime], list[Row]] = ([t for t, _ in rows], [r for _, r in rows])

    @property
    def period(self) -> tuple[datetime, datetime]:
        times = self._series[0]
        return times[0], times[-1]

    @property
    def latest(self) -> datetime:
        return self._series[0][-1]

    def extend(self, rows: list[tuple[datetime, Row]]) -> int:
        """Add or replace hours; returns how many hours are new."""
        times, current = self._series
        merged = dict(zip(times, current))
        added = sum(1 for stamp, _ in rows if stamp not in merged)
        merged.update(rows)
        ordered = sorted(merged)
        self._series = (ordered, [merged[stamp] for stamp in ordered])
        return added

    def _row(self, stamp: datetime) -> Row | None:
        times, rows = self._series
        index = bisect_left(times, stamp)
        if index < len(times) and times[index] == stamp:
            return rows[index]
        return None

    def _last_value(self, stamp: datetime, column: str) -> float | None:
        """Value at ``stamp``, or the latest one within MISSING_FILL before it.

        Single hours go missing in live data (API허브 reported no cloud amount
        for 청주 at 19:00 on 2026-09-27), and that must not make "now" unanswerable.
        """
        for back in range(int(MISSING_FILL / HOUR) + 1):
            row = self._row(stamp - back * HOUR)
            if row is not None and row.get(column) is not None:
                return row[column]
        return None

    def _state(self, when: datetime, column: str) -> float:
        before = when.replace(minute=0, second=0, microsecond=0)
        after = before if before == when else before + HOUR
        low_value = self._last_value(before, column)
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
        if extraterrestrial < MIN_RELIABLE_EXTRATERRESTRIAL:
            cloud = min(max((self._last_value(hour_end, "cloud") or 0.0) / 10.0, 0.0), 1.0)
            return clearness_from_cloud(cloud), mean_global
        return min(mean_global / extraterrestrial, 1.0), mean_global

    def at(self, when: datetime) -> WeatherSample:
        when = localize_datetime(when)
        start, latest = self.period
        if when < start or when > latest + PERSISTENCE_LIMIT:
            raise WeatherUnavailable(
                f"weather is available from {start:%Y-%m-%d %H:%M} to "
                f"{latest + PERSISTENCE_LIMIT:%Y-%m-%d %H:%M} (Asia/Seoul)"
            )

        persisted = when > latest
        if persisted:
            # Carry the latest hour forward, both its state and its cloudiness.
            state_at, hour_end, observed_at = latest, latest, latest
        else:
            state_at = when
            hour_end = when.replace(minute=0, second=0, microsecond=0)
            if hour_end < when:
                hour_end += HOUR
            observed_at = hour_end
        clearness, hour_mean = self._clearness(hour_end)

        altitude = calculate_solar_position(when, self.latitude, self.longitude).altitude
        global_now = clearness * extraterrestrial_horizontal(when.timetuple().tm_yday, altitude)
        return WeatherSample(
            when=when,
            observed_at=observed_at,
            persisted=persisted,
            air_temp_c=self._state(state_at, "ta"),
            relative_humidity=self._state(state_at, "hm"),
            dew_point_c=self._state(state_at, "td"),
            vapour_hpa=self._state(state_at, "pv"),
            wind_ms=self._state(state_at, "ws"),
            cloud_fraction=min(max(self._state(state_at, "cloud") / 10.0, 0.0), 1.0),
            clearness_index=clearness,
            global_horizontal=max(global_now, 0.0),
            hour_mean_global_horizontal=hour_mean,
        )
