"""Clip the 환경부 세분류 토지피복지도 to the campus and group it for the model.

The land cover tells the microclimate model where trees are (they shade and
let some sun through) and what the ground is made of (how much sun it
reflects and how hot it gets). The ~30 세분류 classes collapse into the few
surface types the model distinguishes; their physical parameters live in
backend/app/services/surfaces.py, not here, so they can be tuned without
rebuilding this file.

Street trees are not in the 토지피복지도 - a tree-lined road is classified as
road - and are added separately in data/cbnu_street_trees.geojson.

Input: the two 세분류 SHP folders in data/raw/landcover/ (도엽 36706049,
36706059; see docs/03-data-collection.md). data/raw is not committed; the
output is.

    python scripts/build_landcover.py
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import shape

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw" / "landcover"
BOUNDARY_PATH = ROOT / "data" / "cbnu_campus_boundary.geojson"
OUTPUT_PATH = ROOT / "data" / "cbnu_landcover.geojson"

CRS = "EPSG:5179"
# Trees just outside the campus still shade paths along its edge.
MARGIN_M = 100.0
# Coordinates in the output, in degrees; 1e-6 is about 0.1 m.
PRECISION = 6

# 세분류 L3_CODE -> surface type. Built-up classes (주거, 상업, 교육, 도로 ...)
# describe land use, not the surface; on the ground they are pavement and
# buildings, and buildings come from the building layer, so they map to paved.
SURFACE_BY_CODE = {
    311: "tree_broadleaf",  # 활엽수림
    321: "tree_conifer",  # 침엽수림
    331: "tree_mixed",  # 혼효림
    411: "grass",  # 자연초지
    422: "grass",  # 묘지
    423: "grass",  # 기타초지
    212: "field",  # 경지정리가 안 된 논
    222: "field",  # 경지정리가 안 된 밭
    231: "field",  # 시설재배지
    241: "field",  # 과수원
    251: "field",  # 목장·양식장
    252: "field",  # 기타재배지
    511: "grass",  # 내륙습지
    613: "bare",  # 암벽·바위
    622: "bare",  # 운동장
    623: "bare",  # 기타나지
    711: "water",  # 하천
    712: "water",  # 호소
}
DEFAULT_SURFACE = "paved"  # every 시가화건조지역 class (1xx)


def main() -> None:
    folders = sorted(RAW_DIR.glob("SG05_*"))
    if not folders:
        raise SystemExit(f"no 토지피복지도 folders in {RAW_DIR} (see docs/03-data-collection.md)")
    frames = [gpd.read_file(next(folder.glob("*.shp")), encoding="cp949") for folder in folders]
    cover = pd.concat(frames, ignore_index=True).to_crs(CRS)

    boundary = gpd.GeoSeries(
        [shape(json.loads(BOUNDARY_PATH.read_text(encoding="utf-8"))["features"][0]["geometry"])],
        crs="EPSG:4326",
    ).to_crs(CRS)
    area = boundary.buffer(MARGIN_M).iloc[0]
    cover = cover[cover.intersects(area)].copy()
    cover["geometry"] = cover.intersection(area)
    cover = cover[~cover.is_empty]

    cover["surface"] = [SURFACE_BY_CODE.get(int(code), DEFAULT_SURFACE) for code in cover["L3_CODE"]]
    unknown = sorted({int(c) for c in cover["L3_CODE"] if int(c) not in SURFACE_BY_CODE and int(c) // 100 != 1})
    if unknown:
        raise SystemExit(f"unmapped 세분류 codes {unknown}; add them to SURFACE_BY_CODE")

    # Merge touching polygons of the same surface type: the model only needs
    # the type, and it keeps the file small.
    merged = cover.dissolve(by="surface").explode(index_parts=False).reset_index()
    merged = merged[merged.area >= 1.0].to_crs("EPSG:4326")
    merged["geometry"] = merged.geometry.set_precision(10**-PRECISION)

    inside_campus = cover[cover.intersects(boundary.iloc[0])]
    share = Counter()
    for surface, geometry in zip(inside_campus["surface"], inside_campus.intersection(boundary.iloc[0])):
        share[surface] += geometry.area
    total = sum(share.values())

    collection = json.loads(merged[["surface", "geometry"]].to_json(drop_id=True))
    collection["name"] = "cbnu_landcover"
    collection["metadata"] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "환경부 세분류 토지피복지도 2025 (도엽 36706049, 36706059, 2024년 영상 기준)",
        "area": f"campus boundary + {MARGIN_M:g} m",
        "note": "built-up land-use classes are mapped to 'paved'; street trees are not included "
        "(see cbnu_street_trees.geojson)",
        "campus_share": {key: round(value / total, 4) for key, value in share.most_common()},
    }
    OUTPUT_PATH.write_text(json.dumps(collection, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"wrote {OUTPUT_PATH.name}: {len(merged)} polygons, "
          f"{OUTPUT_PATH.stat().st_size / 1024:.0f} KB")
    for surface, value in share.most_common():
        print(f"  {surface:15s} {value / total * 100:5.1f}% of campus")


if __name__ == "__main__":
    main()
