"""Fetch hourly 기상청 ASOS observations for the 청주 station (131).

The microclimate model needs, for any hour it is asked about, the air
temperature, humidity, wind and - above all - the global solar radiation that
the shade map switches on and off. 청주 is the only ASOS station that measures
all of these near the campus, including 일사 (icsr).

The API only serves data up to yesterday, so the result is a committed snapshot
like every other file in data/; the API never calls this at runtime.

    DATA_GO_KR_API_KEY=... python scripts/fetch_kma_asos.py --start 2025-06-01 --end 2026-09-26
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import os

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
OUTPUT_PATH = DATA_DIR / "kma_asos_131_hourly.csv"
META_PATH = DATA_DIR / "kma_asos_131_hourly.meta.json"

ENDPOINT = "https://apis.data.go.kr/1360000/AsosHourlyInfoService/getWthrDataList"
STATION_ID = "131"

# A page holds at most 999 rows, so each request covers one month (<= 744 hours).
PAGE_SIZE = 999

# Output column -> ASOS field. Everything else in the response (visibility,
# snow, soil temperatures at depth, QC flags) is not used by the model.
FIELDS = {
    "ta": "ta",          # air temperature, °C
    "hm": "hm",          # relative humidity, %
    "td": "td",          # dew point, °C
    "pv": "pv",          # vapour pressure, hPa
    "ws": "ws",          # wind speed at 10 m, m/s
    "wd": "wd",          # wind direction, degrees
    "icsr": "icsr",      # global solar radiation over the past hour, MJ/m²
    "ss": "ss",          # sunshine over the past hour, h
    "cloud": "dc10Tca",  # total cloud amount, tenths (0-10)
    "ts": "ts",          # ground surface temperature, °C
}


def month_ranges(start: date, end: date):
    current = start
    while current <= end:
        next_month = (current.replace(day=1) + timedelta(days=32)).replace(day=1)
        yield current, min(end, next_month - timedelta(days=1))
        current = next_month


def request(key: str, start: date, end: date) -> list[dict]:
    completed = subprocess.run(
        [
            "curl", "-s", "--fail", "--max-time", "60", "-G", ENDPOINT,
            "--data-urlencode", f"serviceKey={key}",
            "--data-urlencode", "dataType=JSON",
            "--data-urlencode", "dataCd=ASOS",
            "--data-urlencode", "dateCd=HR",
            "--data-urlencode", f"startDt={start:%Y%m%d}",
            "--data-urlencode", "startHh=00",
            "--data-urlencode", f"endDt={end:%Y%m%d}",
            "--data-urlencode", "endHh=23",
            "--data-urlencode", f"stnIds={STATION_ID}",
            "--data-urlencode", f"numOfRows={PAGE_SIZE}",
            "--data-urlencode", "pageNo=1",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(completed.stdout)
    response = payload.get("response", {})
    header = response.get("header", {})
    if header.get("resultCode") != "00":
        raise SystemExit(f"ASOS API error for {start}..{end}: {header}")
    body = response.get("body", {})
    items = (body.get("items") or {}).get("item") or []
    if int(body.get("totalCount", 0)) != len(items):
        raise SystemExit(
            f"{start}..{end}: got {len(items)} of {body.get('totalCount')} rows; page size is off"
        )
    return items


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=date.fromisoformat, default=date(2025, 6, 1))
    parser.add_argument(
        "--end", type=date.fromisoformat, default=date.today() - timedelta(days=1)
    )
    args = parser.parse_args()

    key = os.environ.get("DATA_GO_KR_API_KEY")
    if not key:
        raise SystemExit("DATA_GO_KR_API_KEY is not set (see .env.example)")

    rows: list[dict] = []
    for start, end in month_ranges(args.start, args.end):
        items = request(key, start, end)
        for item in items:
            row = {"tm": item["tm"]}
            row.update({column: item.get(field, "") for column, field in FIELDS.items()})
            rows.append(row)
        print(f"  {start:%Y-%m}  {len(items):>4} hours")

    with OUTPUT_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["tm", *FIELDS])
        writer.writeheader()
        writer.writerows(rows)

    with_radiation = sum(1 for row in rows if row["icsr"] not in ("", None))
    META_PATH.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "source": "기상청 지상(종관, ASOS) 시간자료 조회서비스 (getWthrDataList)",
                "station": {"id": STATION_ID, "name": "청주"},
                "period": {"start": args.start.isoformat(), "end": args.end.isoformat()},
                "hours": len(rows),
                "timezone": "Asia/Seoul",
                "note": "icsr is the radiation accumulated over the hour ending at tm; "
                "blank icsr means no radiation (night) or a missing value",
                "columns": {column: field for column, field in FIELDS.items()},
                "hours_with_icsr": with_radiation,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"\nwrote {OUTPUT_PATH.name}: {len(rows)} hours, icsr present in {with_radiation}")


if __name__ == "__main__":
    main()
