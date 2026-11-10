"""Campus environment sensors (Raspberry Pi + temperature/CO2), read from export files.

The course network hands out one file per sensor: a reading about every 10 s
with ``received_at`` (KST, whole seconds), ``timestamp`` (Unix, fractional),
``sensor``, ``mac``, ``temp`` (°C), ``co2`` (ppm), ``lat``/``lon``. The files
carry real gaps and faulty values, so every reading gets quality flags here
and only clean temperatures go into the averages.

``timestamp`` is the measurement time; ``received_at`` is the same instant cut
to the second, so it is kept only to spot clock trouble.

Not used by the heatmap yet: this is the input to the sensor test
(scripts/analyze_sensors.py) that decides whether v2 corrects air temperature
from sensors (docs/04-data-usage-plan.md §5).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import shapely
from shapely.geometry.base import BaseGeometry

TIMEZONE = "Asia/Seoul"

TEMP_RANGE_C = (-30.0, 50.0)
# A reading this far from the median of its neighbours (about a minute either
# side) is a single bad sample; real air does not jump 1.5 °C and back in 20 s.
SPIKE_WINDOW = 7
SPIKE_LIMIT_C = 1.5
# The same float repeated this many times (~5 min) means a hung sensor.
STUCK_RUN = 30
# Positions are typed in by hand; anything this far from the sensor's usual
# spot is a different site or a typo.
MOVED_M = 20.0
# The CO2 chip reports exactly 400 ppm while it warms up or loses its baseline
# and pins at 65000 ppm when it fails; neither is a measurement.
CO2_FLOOR_PPM = 400
CO2_SATURATED_PPM = 65000

COLUMNS = ["sensor", "mac", "time", "received_at", "temp", "co2", "lat", "lon"]


def load_readings(path: Path) -> pd.DataFrame:
    """One export file (CSV or JSON) as a frame sorted by sensor and time."""
    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            payload = next(value for value in payload.values() if isinstance(value, list))
        raw = pd.DataFrame(payload)
    else:
        # utf-8-sig: the exports start with a byte order mark.
        raw = pd.read_csv(path, encoding="utf-8-sig")

    frame = pd.DataFrame(
        {
            "sensor": raw["sensor"].astype(str).str.strip(),
            "mac": raw["mac"].astype(str).str.upper(),
            "time": pd.to_datetime(pd.to_numeric(raw["timestamp"], errors="coerce"), unit="s", utc=True)
            .dt.tz_convert(TIMEZONE),
            "received_at": pd.to_datetime(raw["received_at"], errors="coerce").dt.tz_localize(TIMEZONE),
        }
    )
    for column in ("temp", "co2", "lat", "lon"):
        frame[column] = pd.to_numeric(raw[column], errors="coerce")
    return frame.sort_values(["sensor", "time"], kind="stable").reset_index(drop=True)


def load_directory(directory: Path) -> pd.DataFrame:
    files = sorted(p for p in directory.iterdir() if p.suffix.lower() in (".csv", ".json"))
    if not files:
        raise FileNotFoundError(f"no sensor CSV/JSON files in {directory}")
    frames = [load_readings(path) for path in files]
    combined = pd.concat(frames, ignore_index=True)
    return combined.sort_values(["sensor", "time"], kind="stable").reset_index(drop=True)


def _add(flags: pd.Series, mask: pd.Series, name: str) -> pd.Series:
    return flags.where(~mask, flags + name + ";")


def _distance_m(lon: pd.Series, lat: pd.Series, lon0: float, lat0: float) -> pd.Series:
    """Equirectangular distance; exact enough over a campus."""
    dx = (lon - lon0) * 111_320.0 * np.cos(np.radians(lat0))
    dy = (lat - lat0) * 110_540.0
    return np.hypot(dx, dy)


def flag_quality(readings: pd.DataFrame, campus: BaseGeometry | None = None) -> pd.DataFrame:
    """Add ``qc`` (';'-separated reasons, '' when clean), ``temp_ok`` and ``co2_ok``.

    Temperature flags: missing, range, duplicate, spike, stuck, location.
    CO2 flags: co2_missing, co2_floor, co2_saturated. A CO2 fault does not
    make the temperature of the same reading bad.
    """
    out = readings.copy()
    flags = pd.Series("", index=out.index)

    temp = out["temp"]
    flags = _add(flags, temp.isna() | out["time"].isna(), "missing")
    low, high = TEMP_RANGE_C
    flags = _add(flags, temp.notna() & ((temp < low) | (temp > high)), "range")
    flags = _add(flags, out.duplicated(["sensor", "time"], keep="first") & out["time"].notna(), "duplicate")

    usable = flags == ""
    by_sensor = out["sensor"]
    clean_temp = temp.where(usable)
    median = clean_temp.groupby(by_sensor).transform(
        lambda s: s.dropna().rolling(SPIKE_WINDOW, center=True, min_periods=3).median().reindex(s.index)
    )
    flags = _add(flags, usable & ((temp - median).abs() > SPIKE_LIMIT_C), "spike")

    run_id = (temp != temp.groupby(by_sensor).shift()).cumsum()
    run_length = temp.groupby([by_sensor, run_id]).transform("size")
    flags = _add(flags, temp.notna() & (run_length >= STUCK_RUN), "stuck")

    misplaced = out["lon"].isna() | out["lat"].isna()
    for _, group in out.groupby("sensor"):
        lon0, lat0 = _usual_position(group)
        misplaced.loc[group.index] |= _distance_m(group["lon"], group["lat"], lon0, lat0) > MOVED_M
    if campus is not None:
        misplaced |= ~shapely.contains_xy(campus, out["lon"].to_numpy(), out["lat"].to_numpy())
    flags = _add(flags, misplaced, "location")

    out["temp_ok"] = flags == ""

    co2 = out["co2"]
    flags = _add(flags, co2.isna(), "co2_missing")
    flags = _add(flags, co2 == CO2_FLOOR_PPM, "co2_floor")
    flags = _add(flags, co2 >= CO2_SATURATED_PPM, "co2_saturated")
    out["co2_ok"] = ~(co2.isna() | (co2 == CO2_FLOOR_PPM) | (co2 >= CO2_SATURATED_PPM))
    out["qc"] = flags
    return out


def _usual_position(group: pd.DataFrame) -> tuple[float, float]:
    positions = group[["lon", "lat"]].dropna().round(6)
    if positions.empty:
        return float("nan"), float("nan")
    lon, lat = positions.value_counts().idxmax()
    return float(lon), float(lat)


def flag_counts(flagged: pd.DataFrame) -> pd.DataFrame:
    """Readings per sensor and reason; a reading can count under several reasons."""
    reasons = flagged["qc"].str.rstrip(";").str.split(";").explode()
    reasons = reasons[reasons != ""]
    table = pd.crosstab(
        flagged.loc[reasons.index, "sensor"].to_numpy(), reasons.to_numpy(), rownames=["sensor"]
    )
    table.insert(0, "readings", flagged.groupby("sensor").size())
    table["temp_ok_pct"] = (flagged.groupby("sensor")["temp_ok"].mean() * 100).round(1)
    return table.fillna(0)
