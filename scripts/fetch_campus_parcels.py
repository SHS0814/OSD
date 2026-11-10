"""Collect the land parcels (PNU) the campus buildings stand on.

The building ledger API is addressed by parcel, not by coordinate, so this turns
the campus polygon into the handful of PNUs that cover it. Parcel identity comes
from VWorld's GIS건물통합정보 layer, which carries a PNU for every building
footprint even when no ledger record is attached to it.

Run once and commit the result; scripts/fetch_building_ledger.py reads it, so the
ledger step needs no VWorld key.

    VWORLD_API_KEY=... python scripts/fetch_campus_parcels.py
"""

from __future__ import annotations

import itertools
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import shape
from shapely.ops import transform as transform_geometry

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
BOUNDARY_PATH = DATA_DIR / "cbnu_campus_boundary.geojson"
OUTPUT_PATH = DATA_DIR / "cbnu_campus_parcels.json"

WFS_URL = "https://api.vworld.kr/ned/wfs/getBldgisSpceWFS"
LAYER = "dt_d010"

# The layer is served from a Web Mercator store: a bbox given in any other CRS
# silently returns nothing, and the geometry comes back in metres, not degrees.
# The published reference's "EPSG:4326 uses ymin,xmin order" note does not apply.
SERVER_CRS = "EPSG:3857"
MAX_FEATURES = 1000
TILES = 3


def fetch_tile(key: str, domain: str, box: tuple[float, float, float, float]) -> dict:
    """Fetch one bbox tile. Uses curl so an intercepting TLS proxy does not break it."""
    minx, miny, maxx, maxy = box
    completed = subprocess.run(
        [
            "curl", "-s", "--fail", "--max-time", "90", "-G", WFS_URL,
            "--data-urlencode", f"key={key}",
            "--data-urlencode", f"domain={domain}",
            "--data-urlencode", f"typename={LAYER}",
            "--data-urlencode", f"bbox={minx},{miny},{maxx},{maxy}",
            "--data-urlencode", f"maxFeatures={MAX_FEATURES}",
            "--data-urlencode", "output=application/json",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(completed.stdout)


def split_pnu(pnu: str) -> dict[str, str]:
    """Split a 19-digit PNU into the fields the building ledger API expects.

    Layout: sido(2) sigungu(3) eupmyeondong(3) ri(2) mountain(1) bun(4) ji(4).
    The mountain digit is 1 for ordinary land and 2 for a mountain parcel, while
    the ledger's platGbCd uses 0 and 1 for the same distinction.
    """
    return {
        "pnu": pnu,
        "sigunguCd": pnu[0:5],
        "bjdongCd": pnu[5:10],
        "platGbCd": "1" if pnu[10] == "2" else "0",
        "bun": pnu[11:15],
        "ji": pnu[15:19],
    }


def main() -> None:
    key = os.environ.get("VWORLD_API_KEY")
    if not key:
        raise SystemExit("VWORLD_API_KEY is not set (see .env.example)")
    domain = os.environ.get("VWORLD_DOMAIN", "")

    boundary = shape(json.loads(BOUNDARY_PATH.read_text(encoding="utf-8"))["features"][0]["geometry"])
    to_server = Transformer.from_crs("EPSG:4326", SERVER_CRS, always_xy=True)
    to_wgs84 = Transformer.from_crs(SERVER_CRS, "EPSG:4326", always_xy=True)

    minx, miny, maxx, maxy = boundary.bounds
    x1, y1 = to_server.transform(minx, miny)
    x2, y2 = to_server.transform(maxx, maxy)

    features: dict[str, dict] = {}
    for row, column in itertools.product(range(TILES), range(TILES)):
        tile = (
            x1 + (x2 - x1) * row / TILES,
            y1 + (y2 - y1) * column / TILES,
            x1 + (x2 - x1) * (row + 1) / TILES,
            y1 + (y2 - y1) * (column + 1) / TILES,
        )
        payload = fetch_tile(key, domain, tile)
        returned = payload.get("features", [])
        if payload.get("totalFeatures", 0) > len(returned):
            raise SystemExit(
                f"tile {row},{column} hit the {MAX_FEATURES}-feature cap; raise TILES and rerun"
            )
        for feature in returned:
            features[feature["properties"]["gis_idntfc_no"]] = feature

    inside = []
    for feature in features.values():
        point = transform_geometry(to_wgs84.transform, shape(feature["geometry"])).representative_point()
        if boundary.contains(point):
            inside.append(feature["properties"])

    with_ledger = sum(1 for p in inside if str(p.get("use_confm_de", ""))[:4].isdigit())
    parcels = sorted({p["pnu"] for p in inside if p.get("pnu")})

    OUTPUT_PATH.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "source": "VWorld GIS건물통합정보 (dt_d010)",
                "campus_building_count": len(inside),
                "buildings_with_ledger_attributes": with_ledger,
                "parcel_count": len(parcels),
                "parcels": [split_pnu(pnu) for pnu in parcels],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"wrote {OUTPUT_PATH.name}")
    print(f"  campus building footprints  {len(inside)}")
    print(f"  of which carry ledger data  {with_ledger}")
    print(f"  distinct parcels to query   {len(parcels)}")


if __name__ == "__main__":
    main()
