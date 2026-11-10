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

import pandas as pd

TIMEZONE = "Asia/Seoul"


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
