"""Sensor export loading and quality flags on small hand-made files."""

import json
from pathlib import Path

import pandas as pd
import pytest
from shapely.geometry import Point, box

from app.services import sensors
from app.services.geometry import to_projected
from app.services.microclimate import CELL_M, MicroclimateModel

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


def test_clean_readings_have_no_flags(tmp_path: Path) -> None:
    flagged = sensors.flag_quality(sensors.load_readings(write_csv(tmp_path / "s.csv", steady(20))))
    assert flagged["temp_ok"].all()
    assert (flagged["qc"] == "").all()


@pytest.mark.parametrize(
    ("row", "reason"),
    [
        ((95.0, 85.0, 800), "range"),
        ((95.0, "", 800), "missing"),
        ((95.0, 24.0, 800), "spike"),
        ((95.0, 20.0, 800, 36.6300, LON), "location"),
    ],
)
def test_bad_temperature_is_flagged(tmp_path: Path, row: tuple, reason: str) -> None:
    flagged = sensors.flag_quality(sensors.load_readings(write_csv(tmp_path / "s.csv", steady(20) + [row])))
    assert reason in flags_of(flagged, 95.0)
    assert flagged["temp_ok"].sum() == 20


def test_duplicate_keeps_the_first(tmp_path: Path) -> None:
    flagged = sensors.flag_quality(sensors.load_readings(write_csv(tmp_path / "s.csv", steady(5) + [(20.0, 20.0, 800)])))
    assert flagged["qc"].str.contains("duplicate").sum() == 1


def test_stuck_value_is_flagged(tmp_path: Path) -> None:
    rows = [(i * 10.0, 20.0, 800) for i in range(sensors.STUCK_RUN)]
    flagged = sensors.flag_quality(sensors.load_readings(write_csv(tmp_path / "s.csv", rows)))
    assert flagged["qc"].str.contains("stuck").all()


def test_outside_campus_is_flagged(tmp_path: Path) -> None:
    campus = box(LON - 0.01, LAT - 0.01, LON + 0.01, LAT + 0.01)
    far = box(LON + 1, LAT + 1, LON + 2, LAT + 2)
    readings = sensors.load_readings(write_csv(tmp_path / "s.csv", steady(3)))
    assert sensors.flag_quality(readings, campus)["temp_ok"].all()
    assert not sensors.flag_quality(readings, far)["temp_ok"].any()


def test_co2_faults_do_not_spoil_temperature(tmp_path: Path) -> None:
    rows = steady(5) + [(55.0, 20.0, sensors.CO2_FLOOR_PPM), (65.0, 20.01, sensors.CO2_SATURATED_PPM)]
    flagged = sensors.flag_quality(sensors.load_readings(write_csv(tmp_path / "s.csv", rows)))
    assert flags_of(flagged, 55.0) == "co2_floor;"
    assert flags_of(flagged, 65.0) == "co2_saturated;"
    assert flagged["temp_ok"].all()
    assert flagged["co2_ok"].sum() == 5


def test_counts_and_sites(tmp_path: Path) -> None:
    rows = steady(20) + [(95.0, 85.0, sensors.CO2_FLOOR_PPM)]
    flagged = sensors.flag_quality(sensors.load_readings(write_csv(tmp_path / "s.csv", rows)))
    counts = sensors.flag_counts(flagged)
    assert counts.loc["sensor 20", "readings"] == 21
    assert counts.loc["sensor 20", "range"] == 1
    assert counts.loc["sensor 20", "co2_floor"] == 1
    site = sensors.sites(flagged).loc["sensor 20"]
    assert (site["lat"], site["lon"]) == (LAT, LON)
    assert site["readings"] == 21


def test_resample_drops_thin_bins_and_labels_like_asos(tmp_path: Path) -> None:
    # A full first hour (360 readings) and 10 readings in the second.
    rows = steady(360) + [(3600.0 + i * 10.0, 30.0, 800) for i in range(10)]
    flagged = sensors.flag_quality(sensors.load_readings(write_csv(tmp_path / "s.csv", rows)))
    hourly = sensors.resample(flagged, "1h", label="right")
    # closed="right": the lone reading at exactly 00:00 makes a thin bin ending
    # 00:00, and the 10 readings after 01:00 a thin one ending 02:00; both go.
    assert len(hourly) == 1
    first = hourly.iloc[0]
    assert first["time"] == pd.Timestamp("2026-09-28 01:00", tz="Asia/Seoul")
    assert first["temp"] == pytest.approx(20.0, abs=0.02)
    assert first["coverage"] > 0.9


def test_grid_cell_finds_the_cell() -> None:
    model = MicroclimateModel(box(LON - 0.001, LAT - 0.001, LON + 0.001, LAT + 0.001), [])
    row, col = sensors.grid_cell(model.grid, LON, LAT)
    point = to_projected(Point(LON, LAT))
    assert abs(point.x - (model.grid.origin_x + (col + 0.5) * CELL_M)) <= CELL_M / 2
    assert abs(point.y - (model.grid.origin_y - (row + 0.5) * CELL_M)) <= CELL_M / 2
    assert sensors.grid_cell(model.grid, LON + 1, LAT) is None
