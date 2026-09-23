"""Resolve a building height from the sources available for the campus.

Precedence, strongest evidence first:

1. 건축물대장 표제부 `heit` matched to the building - a surveyed figure.
2. The same, via a complex whose members are known and whose floor count matches,
   so the registered height applies unscaled (data/cbnu_building_aliases.json).
3. The OSM `height` tag - almost always a whole number, and comparison against the
   ledger shows mappers round down, so it loses to the ledger when both exist.

Floor counts are never converted to metres here. They are carried through as
`building_levels` and `ledger_floors` so the gap stays visible and a later
decision to estimate can be made explicitly rather than by accident.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
LEDGER_PATH = DATA_DIR / "cbnu_building_ledger.json"
ALIASES_PATH = DATA_DIR / "cbnu_building_aliases.json"

# Campus buildings carry an official code such as (N10) or (S1-6) in both the OSM
# name and the ledger's 동명칭, which joins them far better than the names do -
# the ledger calls 학연산공동교육관 "전자정보2관", but both say (E10).
CODE_PATTERN = re.compile(r"\(([A-Z]{1,2}\d{1,2}(?:-\d{1,2})?)\)")

# Guards for the name fallback, which is only reached when no code matches.
# A name match is accepted only when the OSM name is contained in the ledger's,
# never the reverse: the ledger spells the same building out more fully
# (승리관 -> 승리관운동부합숙소), whereas a ledger name appearing inside a longer
# OSM name means a different, smaller thing sits there - the convenience store
# "이마트24 충북대대학본부점" is not 대학본부, and "양현재 관리동" is not 양현재.
# The footprint must agree too, so a kiosk cannot inherit a tower's height.
NAME_AREA_RATIO = (0.5, 2.0)


@dataclass(frozen=True)
class Height:
    metres: float | None
    source: str | None
    ledger_floors: float | None
    match: str | None


def _positive(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def building_code(text: str | None) -> str | None:
    found = CODE_PATTERN.search(str(text or "").replace(" ", ""))
    return found.group(1) if found else None


def _bare_name(text: str | None) -> str:
    return re.sub(r"\([^)]*\)", "", str(text or "")).replace(" ", "")


def _name_tokens(text: str | None) -> set[str]:
    """Every name a ledger record can reasonably be looked up by.

    A record may nest the building's own name inside the complex's, as in
    "개성재(정의관)(N17-4)". Stripping all brackets would leave only 개성재 and
    lose 정의관, which is what OSM calls that building, so the bracketed parts are
    kept as lookup names too - except the (N17-4) style code, handled separately.
    """
    raw = str(text or "")
    tokens = {_bare_name(raw)}
    for inner in re.findall(r"\(([^)]*)\)", raw):
        candidate = inner.replace(" ", "")
        if candidate and not CODE_PATTERN.fullmatch(f"({candidate})"):
            tokens.add(candidate)
    return {token for token in tokens if token}


class HeightResolver:
    def __init__(self) -> None:
        payload = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
        self.records = payload["records"]

        self.by_code: dict[str, list[dict]] = {}
        self.by_name: dict[str, list[dict]] = {}
        for record in self.records:
            code = building_code(record.get("dongNm")) or building_code(record.get("bldNm"))
            if code:
                self.by_code.setdefault(code, []).append(record)
            for name in _name_tokens(record.get("dongNm")) | _name_tokens(record.get("bldNm")):
                self.by_name.setdefault(name, []).append(record)

        aliases = json.loads(ALIASES_PATH.read_text(encoding="utf-8"))
        # Buildings the team identified by campus code. The ledger files these
        # under bare codes ("N3-1동") that neither a code nor a name match can
        # reach, so the mapping is stated outright and skips the area guard.
        self.explicit_code = {
            entry["osm_name"]: entry["ledger_code"] for entry in aliases.get("buildings", [])
        }
        # Only complexes whose floor count matches every member can lend their
        # height unchanged; the rest would silently overstate the shorter towers.
        self.member_to_complex: dict[str, dict] = {}
        for complex_entry in aliases["complexes"]:
            if complex_entry["confidence"] != "high":
                continue
            for member in complex_entry["members"]:
                self.member_to_complex[member] = complex_entry

    def _closest_by_area(self, records: list[dict], footprint_m2: float) -> dict | None:
        """Pick the record whose 건축면적 is nearest the footprint.

        A code can be shared by a building and its outbuildings - (E7-1) covers
        both the 1,434 m2 의과대학 and a 10 m2 의료폐기물저장소 - and only the
        latter happens to carry a height.
        """
        if not records:
            return None
        scored = []
        for index, record in enumerate(records):
            area = _positive(record.get("archArea"))
            distance = abs(area - footprint_m2) if area else float("inf")
            scored.append((distance, index, record))
        return min(scored, key=lambda item: (item[0], item[1]))[2]

    def _ledger_record(self, name: str, footprint_m2: float) -> tuple[dict | None, str | None]:
        code = building_code(name)
        if code and code in self.by_code:
            return self._closest_by_area(self.by_code[code], footprint_m2), "code"

        bare = _bare_name(name)
        if bare:
            matches = [
                record
                for key, records in self.by_name.items()
                if key and bare in key
                for record in records
            ]
            best = self._closest_by_area(matches, footprint_m2)
            if best is not None:
                area = _positive(best.get("archArea"))
                low, high = NAME_AREA_RATIO
                if area and low <= footprint_m2 / area <= high:
                    return best, "name"
        return None, None

    def resolve(self, name: str, footprint_m2: float, osm_height: float | None) -> Height:
        code = self.explicit_code.get(name)
        if code:
            for candidate in self.by_code.get(code, []):
                height = _positive(candidate.get("heit"))
                if height is not None:
                    return Height(
                        height,
                        "건축물대장:heit",
                        _positive(candidate.get("grndFlrCnt")),
                        f"team:{code}",
                    )

        record, how = self._ledger_record(name, footprint_m2)
        floors = _positive(record.get("grndFlrCnt")) if record else None

        if record:
            height = _positive(record.get("heit"))
            if height is not None:
                return Height(height, "건축물대장:heit", floors, how)

        complex_entry = self.member_to_complex.get(name)
        if complex_entry:
            shared = self.by_code.get(complex_entry["ledger_code"], [])
            for candidate in shared:
                height = _positive(candidate.get("heit"))
                if height is not None:
                    return Height(
                        height,
                        "건축물대장:heit(단지)",
                        floors or _positive(candidate.get("grndFlrCnt")),
                        f"complex:{complex_entry['ledger_code']}",
                    )

        if osm_height is not None:
            return Height(osm_height, "OpenStreetMap:height", floors, how)

        return Height(None, None, floors, how)
