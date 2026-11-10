"""Sensor export loading and quality flags on small hand-made files."""

import json
from pathlib import Path

import pandas as pd
import pytest

from app.services import sensors

HEADER = "﻿received_at,sensor,mac,temp,co2,timestamp,lat,lon,sender\n"
START = 1790521200.0  # 2026-09-28 00:00:00 KST
LAT, LON = 36.62536, 127.455642


def write_csv(path: Path, rows: list[tuple]) -> Path:
    """rows: (seconds after START, temp, co2[, lat, lon])."""
    lines = [HEADER]
    for row in rows:
        offset, temp, co2, *position = row
        lat, lon = position or (LAT, LON)
        stamp = START + offset
        received = pd.Timestamp(stamp, unit="s", tz="UTC").tz_convert("Asia/Seoul").strftime("%Y-%m-%d %H:%M:%S")
        lines.append(f"{received},sensor 20,d8:3a:dd:79:8e:d9,{temp},{co2},{stamp},{lat},{lon},sensor\n")
    path.write_text("".join(lines), encoding="utf-8")
    return path


def steady(count: int, temp: float = 20.0, step: float = 10.0) -> list[tuple]:
    # Alternate a little so a steady sensor is not mistaken for a stuck one.
    return [(i * step, temp + (0.01 if i % 2 else 0.0), 800) for i in range(count)]


def flags_of(flagged: pd.DataFrame, offset: float) -> str:
    when = pd.Timestamp(START + offset, unit="s", tz="UTC").tz_convert("Asia/Seoul")
    return flagged.loc[(flagged["time"] - when).abs() < pd.Timedelta("1ms"), "qc"].iat[0]


def test_load_reads_unix_time_as_kst(tmp_path: Path) -> None:
    readings = sensors.load_readings(write_csv(tmp_path / "s.csv", [(10.5, 21.0, 800), (0.25, 20.0, 800)]))
    assert list(readings.columns) == sensors.COLUMNS
    assert str(readings["time"].dt.tz) == "Asia/Seoul"
    # Sorted by time, and the fraction of a second survives.
    assert readings["time"].iat[0] == pd.Timestamp("2026-09-28 00:00:00.25", tz="Asia/Seoul")
    assert readings["mac"].iat[0] == "D8:3A:DD:79:8E:D9"


def test_load_reads_json_records(tmp_path: Path) -> None:
    record = {
        "received_at": "2026-09-28 00:00:00", "sensor": "sensor 1", "mac": "aa", "temp": 20.5,
        "co2": 420, "timestamp": START, "lat": LAT, "lon": LON,
    }
    path = tmp_path / "s.json"
    path.write_text(json.dumps({"data": [record]}), encoding="utf-8")
    readings = sensors.load_readings(path)
    assert readings["temp"].iat[0] == 20.5
    assert readings["time"].iat[0] == pd.Timestamp("2026-09-28 00:00", tz="Asia/Seoul")
