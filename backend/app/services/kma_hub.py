"""Recent 청주 ASOS hours from the 기상청 API허브.

The committed snapshot (scripts/fetch_kma_asos.py, via 공공데이터포털) stops at
the day it was taken, because that service only serves data up to yesterday.
API허브 carries the same observations within the hour, so the server keeps its
weather current by appending the hours after the snapshot from here. Values
are identical to the 공공데이터포털 ones for the hours both cover.
"""

from __future__ import annotations

import json
import ssl
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

import certifi

from .solar import SEOUL_TZ

PERIOD_ENDPOINT = "https://apihub.kma.go.kr/api/typ01/url/kma_sfctm3.php"
STATION_ID = "131"
# kma_sfctm3 answers at most 31 days per request.
MAX_SPAN = timedelta(days=30)

# Snapshot column -> API허브 field (disp=1 returns JSON with these names).
FIELDS = {
    "ta": "TA",
    "hm": "HM",
    "td": "TD",
    "pv": "PV",
    "ws": "WS",
    "wd": "WD",
    "icsr": "SI",
    "ss": "SS",
    "cloud": "CA_TOT",
    "ts": "TS",
}


def _value(raw) -> float | None:
    """API허브 marks a missing value with a negative sentinel (-9, -99.0, ...)."""
    try:
        number = float(raw)
    except (TypeError, ValueError):
        return None
    return None if number <= -9 else number


# The certifi bundle, not the interpreter's: python.org's macOS build ships no CA
# store until "Install Certificates" is run, and then rejects API허브's chain.
_TLS = ssl.create_default_context(cafile=certifi.where())


def parse_rows(payload: list[dict]) -> list[tuple[datetime, dict[str, float | None]]]:
    rows = []
    for item in payload:
        stamp = datetime.strptime(item["TM"], "%Y%m%d%H%M").replace(tzinfo=SEOUL_TZ)
        rows.append((stamp, {column: _value(item.get(field)) for column, field in FIELDS.items()}))
    return rows


def fetch_hours(key: str, start: datetime, end: datetime) -> list[tuple[datetime, dict]]:
    """Hourly observations from ``start`` to ``end`` inclusive, oldest first."""
    rows: list[tuple[datetime, dict]] = []
    chunk_start = start
    while chunk_start <= end:
        chunk_end = min(end, chunk_start + MAX_SPAN)
        query = urllib.parse.urlencode(
            {
                "tm1": chunk_start.strftime("%Y%m%d%H%M"),
                "tm2": chunk_end.strftime("%Y%m%d%H%M"),
                "stn": STATION_ID,
                "help": 0,
                "disp": 1,
                "authKey": key,
            }
        )
        with urllib.request.urlopen(f"{PERIOD_ENDPOINT}?{query}", timeout=30, context=_TLS) as response:
            body = response.read().decode("euc-kr", errors="replace").strip()
        # An hour range with nothing observed yet comes back as an empty body.
        if body:
            rows.extend(parse_rows(json.loads(body)))
        chunk_start = chunk_end + timedelta(hours=1)
    return rows
