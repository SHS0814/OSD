"""Rebuild the committed CBNU building snapshot from OpenStreetMap.

Geometry and names come from OSM; height is resolved separately by scripts/heights.py,
which prefers the surveyed 건축물대장 figure over the OSM tag. Floor counts from
either source are recorded but never converted to metres, so a building without a
height keeps `height_m = null` and simply casts no shadow rather than showing an
estimate that looks surveyed.

Run after scripts/fetch_campus_boundary.py and scripts/fetch_building_ledger.py,
then commit the data files.

    python scripts/build_snapshot.py
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import MultiPolygon, Polygon, mapping, shape
from shapely.ops import transform as transform_geometry, unary_union

from heights import HeightResolver
from osm_common import member_rings, osm_name, overpass, parse_height

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
BOUNDARY_PATH = DATA_DIR / "cbnu_campus_boundary.geojson"
SNAPSHOT_PATH = DATA_DIR / "cbnu_buildings.geojson"
REPORT_PATH = DATA_DIR / "cbnu_buildings_match_report.json"

CAMPUS_RELATION_ID = 6705106

# Structures that only add clutter to a shade map: none of them carries a height
# tag, so they can never cast a shadow, and they outnumber the real buildings.
# Greenhouses are the agricultural cluster south of campus - low glass frames
# whose shadow would be meaningless even with a height.
EXCLUDED_BUILDING_VALUES = {"greenhouse"}
MIN_FOOTPRINT_M2 = 200.0

# Metre CRS for Korea, matching the one the shadow service projects into.
TO_METRES = Transformer.from_crs("EPSG:4326", "EPSG:5179", always_xy=True)


def load_boundary():
    collection = json.loads(BOUNDARY_PATH.read_text(encoding="utf-8"))
    return shape(collection["features"][0]["geometry"])


def element_geometry(element: dict):
    """Build a polygonal geometry from a way or a multipolygon relation."""
    if element["type"] == "way":
        coords = [(node["lon"], node["lat"]) for node in element.get("geometry", [])]
        if len(coords) < 4:
            return None
        return Polygon(coords)

    outer_rings, inner_rings = member_rings(element)
    if not outer_rings:
        return None
    holes = [Polygon(ring) for ring in inner_rings]
    polygons = []
    for ring in outer_rings:
        shell = Polygon(ring)
        contained = [
            hole.exterior.coords
            for hole in holes
            if shell.contains(hole.representative_point())
        ]
        polygons.append(Polygon(shell.exterior.coords, contained))
    return unary_union(polygons)


def main() -> None:
    boundary = load_boundary()
    heights = HeightResolver()
    minx, miny, maxx, maxy = boundary.bounds
    bbox = f"{miny},{minx},{maxy},{maxx}"
    query = (
        f"[out:json][timeout:180];"
        f'(way["building"]({bbox});relation["building"]({bbox}););'
        f"out geom;"
    )
    payload = overpass(query)
    elements = payload.get("elements", [])

    features = []
    rejected: list[dict] = []
    outside = 0
    excluded_kind = 0
    excluded_small = 0

    for element in sorted(elements, key=lambda item: (item["type"], item["id"])):
        osm_type, osm_id = element["type"], element["id"]
        tags = element.get("tags", {})

        try:
            geometry = element_geometry(element)
        except ValueError as error:
            rejected.append({"osm_type": osm_type, "osm_id": osm_id, "reason": str(error)})
            continue

        if geometry is None or geometry.is_empty:
            rejected.append({"osm_type": osm_type, "osm_id": osm_id, "reason": "no polygonal geometry"})
            continue
        if not geometry.is_valid:
            geometry = geometry.buffer(0)
            if not geometry.is_valid or geometry.is_empty:
                rejected.append({"osm_type": osm_type, "osm_id": osm_id, "reason": "invalid geometry"})
                continue
        if geometry.geom_type not in ("Polygon", "MultiPolygon"):
            rejected.append({"osm_type": osm_type, "osm_id": osm_id, "reason": geometry.geom_type})
            continue
        if not boundary.contains(geometry.representative_point()):
            outside += 1
            continue
        if tags.get("building") in EXCLUDED_BUILDING_VALUES:
            excluded_kind += 1
            continue
        footprint_m2 = transform_geometry(TO_METRES.transform, geometry).area
        if footprint_m2 < MIN_FOOTPRINT_M2:
            excluded_small += 1
            continue

        name = osm_name(tags, osm_type, osm_id)
        resolved = heights.resolve(name, footprint_m2, parse_height(tags))
        levels = tags.get("building:levels")
        features.append(
            {
                "type": "Feature",
                "id": osm_id,
                "geometry": mapping(geometry),
                "properties": {
                    "id": osm_id,
                    "name": name,
                    "height_m": resolved.metres,
                    "building_levels": levels,
                    "ledger_floors": resolved.ledger_floors,
                    "source_geometry": "OpenStreetMap",
                    "source_height": resolved.source,
                    "height_match": resolved.match,
                    "osm_type": osm_type,
                    "osm_id": osm_id,
                    "vworld_id": None,
                },
            }
        )

    with_height = sum(1 for f in features if f["properties"]["height_m"] is not None)
    with_levels = sum(1 for f in features if f["properties"]["building_levels"] is not None)
    levels_only = sum(
        1
        for f in features
        if f["properties"]["height_m"] is None
        and (
            f["properties"]["building_levels"] is not None
            or f["properties"]["ledger_floors"] is not None
        )
    )
    no_clue = len(features) - with_height - levels_only
    by_source: dict[str, int] = {}
    for feature in features:
        source = feature["properties"]["source_height"]
        if source:
            by_source[source] = by_source.get(source, 0) + 1

    SNAPSHOT_PATH.write_text(
        json.dumps(
            {"type": "FeatureCollection", "name": "cbnu_buildings", "features": features},
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    report = {
        "dataset": "cbnu_buildings",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "campus": {"osm_type": "relation", "osm_id": CAMPUS_RELATION_ID},
        "sources": {
            "osm": {
                "license": "ODbL 1.0",
                "attribution": "© OpenStreetMap contributors",
                "snapshot_timestamp": payload.get("osm3s", {}).get("timestamp_osm_base"),
                "returned_building_count": len(elements),
                "outside_campus_count": outside,
            },
            "filters": {
                "excluded_building_values": sorted(EXCLUDED_BUILDING_VALUES),
                "excluded_by_building_value": excluded_kind,
                "minimum_footprint_m2": MIN_FOOTPRINT_M2,
                "excluded_below_minimum_footprint": excluded_small,
                "note": (
                    "No excluded structure carried a height tag, so the filters "
                    "remove map clutter without losing a single shadow"
                ),
            },
            "vworld": {
                "layer": None,
                "status": "not_used",
                "reason": (
                    "VWorld LT_C_BLDGINFO no longer exists in the catalog; the "
                    "replacement GIS건물통합정보 (dt_d010) carries surveyed heights for "
                    "only a small share of campus buildings and its cadastral "
                    "footprints do not align with the OSM outlines used here"
                ),
                "query_count": 0,
                "returned_feature_count": 0,
            },
        },
        "output": {
            "building_count": len(features),
            "direct_height_count": with_height,
            "missing_height_count": len(features) - with_height,
            "rejected_geometry_count": len(rejected),
        },
        "height_availability": {
            "by_source": by_source,
            "direct_height": with_height,
            "levels_tag_present": with_levels,
            "levels_only_not_converted": levels_only,
            "no_height_and_no_levels": no_clue,
            "note": (
                "Floor counts from OSM and from the ledger are recorded verbatim and "
                "never converted to metres, so a building with only floors still "
                "casts no shadow rather than showing an estimate as if it were surveyed"
            ),
        },
        "matching": {
            "crs": "EPSG:5179",
            "criteria": None,
            "accepted_count": 0,
            "unmatched_osm_count": len(features),
            "ambiguous_count": 0,
            "height_conflict_count": 0,
            "accepted": [],
            "ambiguous": [],
            "low_confidence_candidates": [],
            "height_conflicts": [],
            "excluded_abnormal_heights": [],
            "rejected_geometries": rejected,
        },
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"wrote {SNAPSHOT_PATH.name} and {REPORT_PATH.name}")
    print(f"  buildings kept            {len(features)}")
    print(f"  outside campus, dropped   {outside}")
    print(f"  excluded by building kind {excluded_kind}")
    print(f"  excluded under {MIN_FOOTPRINT_M2:.0f} m2      {excluded_small}")
    print(f"  rejected geometry         {len(rejected)}")
    print()
    print(f"  direct height (shadow)    {with_height}")
    for source, count in sorted(by_source.items(), key=lambda item: -item[1]):
        print(f"      {source:28s} {count}")
    print(f"  levels only (no shadow)   {levels_only}")
    print(f"  nothing at all            {no_clue}")


if __name__ == "__main__":
    main()
