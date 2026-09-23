"""Shared helpers for the one-off OpenStreetMap collection scripts.

Neither the API nor the Android app calls these; they exist to regenerate the
committed snapshots under data/ so the result is reproducible and reviewable.
"""

from __future__ import annotations

import json
import ssl
import subprocess
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = "campus-shade-map/0.1 (university project)"

# The main instance rejects anonymous clients and sheds load under pressure, so
# a request is retried against mirrors before giving up.
OVERPASS_ENDPOINTS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
)

# Endpoints closer than this (in degrees, ~0.1 mm) are treated as the same node.
RING_TOLERANCE = 1e-9


def _post(url: str, query: str, timeout: int) -> bytes:
    """POST an Overpass query and return the raw body.

    Falls back to curl when the local TLS chain cannot be verified, which happens
    on machines behind an intercepting proxy: curl trusts the system store that
    the proxy's root was installed into, while Python ships its own CA bundle.
    """
    body = urllib.parse.urlencode({"data": query}).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.URLError as error:
        if not isinstance(error.reason, ssl.SSLCertVerificationError):
            raise
        completed = subprocess.run(
            [
                "curl", "-s", "--fail", "--max-time", str(timeout),
                "-H", f"User-Agent: {USER_AGENT}",
                "--data-urlencode", f"data={query}",
                url,
            ],
            capture_output=True,
            check=True,
        )
        return completed.stdout


def overpass(query: str, timeout: int = 180) -> dict:
    """Run an Overpass query, trying each mirror in turn."""
    failures: list[str] = []
    for endpoint in OVERPASS_ENDPOINTS:
        try:
            raw = _post(endpoint, query, timeout)
        except Exception as error:  # noqa: BLE001 - any transport failure means "try the next mirror"
            failures.append(f"{endpoint}: {error}")
            continue
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # Overpass reports rate limits and runtime errors as an HTML page.
            failures.append(f"{endpoint}: non-JSON response ({len(raw)} bytes)")
    raise SystemExit("Overpass request failed:\n  " + "\n  ".join(failures))


def _same_point(a: tuple[float, float], b: tuple[float, float]) -> bool:
    return abs(a[0] - b[0]) < RING_TOLERANCE and abs(a[1] - b[1]) < RING_TOLERANCE


def stitch_rings(ways: list[list[tuple[float, float]]]) -> list[list[tuple[float, float]]]:
    """Join unordered, arbitrarily directed ways into closed rings."""
    remaining = [list(way) for way in ways if len(way) >= 2]
    rings: list[list[tuple[float, float]]] = []

    while remaining:
        ring = remaining.pop(0)
        while not _same_point(ring[0], ring[-1]):
            for index, candidate in enumerate(remaining):
                if _same_point(ring[-1], candidate[0]):
                    ring.extend(remaining.pop(index)[1:])
                    break
                if _same_point(ring[-1], candidate[-1]):
                    ring.extend(reversed(remaining.pop(index)[:-1]))
                    break
                if _same_point(ring[0], candidate[-1]):
                    ring = remaining.pop(index)[:-1] + ring
                    break
                if _same_point(ring[0], candidate[0]):
                    ring = list(reversed(remaining.pop(index)[1:])) + ring
                    break
            else:
                raise ValueError(f"could not close a ring; {len(remaining)} way(s) unmatched")
        rings.append(ring)
    return rings


def member_rings(element: dict) -> tuple[list, list]:
    """Split a relation's member ways into stitched outer and inner rings."""
    grouped: dict[str, list[list[tuple[float, float]]]] = {"outer": [], "inner": []}
    for member in element.get("members", []):
        role = member.get("role")
        if member["type"] != "way" or role not in grouped or "geometry" not in member:
            continue
        grouped[role].append([(node["lon"], node["lat"]) for node in member["geometry"]])
    return stitch_rings(grouped["outer"]), stitch_rings(grouped["inner"])


def osm_name(tags: dict, osm_type: str, osm_id: int) -> str:
    """Pick a display name the same way the original snapshot did."""
    for key in ("name:ko", "name", "ref"):
        value = tags.get(key)
        if value:
            return value
    return f"OSM {osm_type} {osm_id}"


def parse_height(tags: dict) -> float | None:
    """Return a direct metre height, or None when the tag is absent or not plain metres.

    Level counts are deliberately NOT converted: an estimated height would be
    indistinguishable from a surveyed one once it reaches the map.
    """
    raw = tags.get("height")
    if raw is None:
        return None
    text = str(raw).strip().removesuffix("m").strip()
    try:
        height = float(text)
    except ValueError:
        return None
    return height if height > 0 else None
