"""Fetch 건축물대장 표제부 records for the campus parcels.

VWorld's GIS건물통합정보 layer leaves most campus footprints without any ledger
attributes - the geometry is there but the join to 건축물대장 failed, so height,
floor count and area all come back empty. The ledger itself does hold those
values, so this queries it directly, by parcel, bypassing the broken join.

Reads data/cbnu_campus_parcels.json, so no VWorld key is needed here.

    DATA_GO_KR_API_KEY=... python scripts/fetch_building_ledger.py
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
PARCELS_PATH = DATA_DIR / "cbnu_campus_parcels.json"
OUTPUT_PATH = DATA_DIR / "cbnu_building_ledger.json"

ENDPOINT = "https://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo"

# The service silently caps a page at 100 rows whatever numOfRows asks for, so
# every parcel has to be paged through or records are lost without any error.
PAGE_SIZE = 100
MAX_PAGES = 50

# Kept from each record; the rest of the ledger is owner and permit detail we do
# not need and should not be committing.
FIELDS = (
    "platPlc", "newPlatPlc", "bldNm", "dongNm", "mgmBldrgstPk",
    "heit", "grndFlrCnt", "ugrndFlrCnt", "archArea", "totArea", "platArea",
    "mainPurpsCdNm", "etcPurps", "strctCdNm", "useAprDay",
)


def request_page(key: str, parcel: dict, page: int) -> dict:
    completed = subprocess.run(
        [
            "curl", "-s", "--fail", "--max-time", "60", "-G", ENDPOINT,
            "--data-urlencode", f"serviceKey={key}",
            "--data-urlencode", f"sigunguCd={parcel['sigunguCd']}",
            "--data-urlencode", f"bjdongCd={parcel['bjdongCd']}",
            "--data-urlencode", f"platGbCd={parcel['platGbCd']}",
            "--data-urlencode", f"bun={parcel['bun']}",
            "--data-urlencode", f"ji={parcel['ji']}",
            "--data-urlencode", f"numOfRows={PAGE_SIZE}",
            "--data-urlencode", f"pageNo={page}",
            "--data-urlencode", "_type=json",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(completed.stdout)
    header = payload.get("response", {}).get("header", {})
    if header.get("resultCode") not in (None, "00"):
        raise SystemExit(f"ledger API error for {parcel['pnu']}: {header}")
    return payload.get("response", {}).get("body", {})


def fetch_parcel(key: str, parcel: dict) -> list[dict]:
    records: list[dict] = []
    total = None
    for page in range(1, MAX_PAGES + 1):
        body = request_page(key, parcel, page)
        total = body.get("totalCount", 0) if total is None else total
        items = (body.get("items") or {}).get("item") or []
        if isinstance(items, dict):
            items = [items]
        for item in items:
            record = {field: item.get(field) for field in FIELDS}
            record["pnu"] = parcel["pnu"]
            records.append(record)
        if len(records) >= int(total or 0) or not items:
            break
    if total is not None and len(records) != int(total):
        raise SystemExit(
            f"{parcel['pnu']}: collected {len(records)} of {total} records; paging is off"
        )
    return records


def as_float(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def main() -> None:
    key = os.environ.get("DATA_GO_KR_API_KEY")
    if not key:
        raise SystemExit("DATA_GO_KR_API_KEY is not set (see .env.example)")

    parcels = json.loads(PARCELS_PATH.read_text(encoding="utf-8"))["parcels"]
    records: list[dict] = []
    for parcel in parcels:
        found = fetch_parcel(key, parcel)
        records.extend(found)
        if found:
            print(f"  {parcel['pnu']}  {len(found):>4} records")

    with_height = sum(1 for record in records if as_float(record["heit"]) is not None)
    with_floors = sum(1 for record in records if as_float(record["grndFlrCnt"]) is not None)

    OUTPUT_PATH.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "source": "국토교통부 건축HUB 건축물대장정보 표제부 (getBrTitleInfo)",
                "parcel_count": len(parcels),
                "record_count": len(records),
                "records_with_height": with_height,
                "records_with_ground_floors": with_floors,
                "records": records,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"\nwrote {OUTPUT_PATH.name}")
    print(f"  records        {len(records)}")
    print(f"  with heit      {with_height} ({with_height / len(records) * 100:.1f}%)")
    print(f"  with grndFlrCnt {with_floors} ({with_floors / len(records) * 100:.1f}%)")


if __name__ == "__main__":
    main()
