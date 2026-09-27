from datetime import datetime

from app.services.kma_hub import parse_rows
from app.services.solar import SEOUL_TZ

# Trimmed from a real kma_sfctm3.php?disp=1 response for 청주 at 2026-09-26 12:00.
SAMPLE = [
    {"TM": "202609261200", "STN_ID": "131", "WD": "25", "WS": "2.8", "TA": "23.8",
     "TD": "15.8", "HM": "61", "PV": "18.0", "CA_TOT": "7", "SS": "0.6", "SI": "2.68",
     "TS": "29.8"},
    {"TM": "202609262300", "STN_ID": "131", "WD": "0", "WS": "0.3", "TA": "18.1",
     "TD": "15.2", "HM": "83", "PV": "17.3", "CA_TOT": "0", "SS": "-9", "SI": "-9",
     "TS": "-99.0"},
]


def test_rows_use_snapshot_columns_and_kst() -> None:
    stamp, row = parse_rows(SAMPLE)[0]
    assert stamp == datetime(2026, 9, 26, 12, tzinfo=SEOUL_TZ)
    assert row["ta"] == 23.8
    assert row["icsr"] == 2.68
    assert row["cloud"] == 7


def test_negative_sentinels_become_missing() -> None:
    _, row = parse_rows(SAMPLE)[1]
    assert row["icsr"] is None
    assert row["ss"] is None
    assert row["ts"] is None
    assert row["wd"] == 0
