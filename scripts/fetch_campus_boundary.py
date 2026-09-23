"""Fetch the CBNU campus boundary from OpenStreetMap and store it as GeoJSON.

The campus is OSM relation 6705106, a multipolygon. Overpass returns its member
ways unordered and with arbitrary direction, so they are stitched into closed
rings before the polygon is assembled.

Only the outer rings are used. The relation's 50 inner members are the campus's
own buildings, car parks and pitches, listed that way so the area does not paint
over them when rendered — they are not parcels excluded from the campus. Cutting
them out as holes would push core buildings (자연대 5·6호관, 사회과학대학 본관,
인문대학 본관, 건설공학관 …) outside the boundary.

Run once and commit the result; the API is never called while the app is running.

    python scripts/fetch_campus_boundary.py
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from shapely.geometry import MultiPolygon, Polygon, mapping
from shapely.ops import unary_union
from shapely.validation import make_valid

from osm_common import member_rings, overpass

CAMPUS_RELATION_ID = 6705106
OUTPUT_PATH = Path(__file__).resolve().parents[1] / "data" / "cbnu_campus_boundary.geojson"


def build_boundary(relation: dict) -> MultiPolygon:
    outer_rings, _inner_rings = member_rings(relation)
    if not outer_rings:
        raise SystemExit("relation has no outer ring")

    boundary = unary_union([Polygon(ring) for ring in outer_rings])
    if not boundary.is_valid:
        # A single self-intersection in the traced outline is common; make_valid
        # returns a GeometryCollection, so keep only its polygonal parts.
        repaired = make_valid(boundary)
        parts = [
            part
            for part in getattr(repaired, "geoms", [repaired])
            if part.geom_type in ("Polygon", "MultiPolygon")
        ]
        boundary = unary_union(parts)

    return boundary if boundary.geom_type == "MultiPolygon" else MultiPolygon([boundary])


def main() -> None:
    payload = overpass(f"[out:json][timeout:90];relation({CAMPUS_RELATION_ID});out geom;")
    elements = payload.get("elements", [])
    if not elements:
        raise SystemExit(f"Overpass returned no relation {CAMPUS_RELATION_ID}")

    relation = elements[0]
    boundary = build_boundary(relation)
    tags = relation.get("tags", {})

    feature = {
        "type": "Feature",
        "geometry": mapping(boundary),
        "properties": {
            "name": tags.get("name:ko") or tags.get("name"),
            "name_en": tags.get("name:en"),
            "osm_type": "relation",
            "osm_id": CAMPUS_RELATION_ID,
            "source": "OpenStreetMap",
            "license": "ODbL 1.0",
            "attribution": "© OpenStreetMap contributors",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        },
    }
    OUTPUT_PATH.write_text(
        json.dumps({"type": "FeatureCollection", "features": [feature]}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"wrote {OUTPUT_PATH.name}")
    print(f"  name      {feature['properties']['name']}")
    print(f"  polygons  {len(boundary.geoms)}")
    print(f"  holes     {sum(len(polygon.interiors) for polygon in boundary.geoms)}")
    print(f"  bounds    {tuple(round(value, 6) for value in boundary.bounds)}")


if __name__ == "__main__":
    main()
