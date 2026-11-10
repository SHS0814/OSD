"""Physical parameters of ground surfaces and tree canopies (model v1).

Land cover comes from data/cbnu_landcover.geojson (scripts/build_landcover.py)
and street trees from data/cbnu_street_trees.geojson, which the team fills in
by hand because the 토지피복지도 classifies a tree-lined road as road.

Only GROUND_HEATING for grass is fitted to data (청주 ASOS, see common.py).
The rest are round literature values and are best read as assumptions: they
set how strongly trees and pavement show up, not whether they do.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry

from .common import GROUND_HEATING_K_PER_W, in_leaf
from .geometry import to_projected


@dataclass(frozen=True)
class Surface:
    albedo: float
    # Kelvin of ground warming above the air per W/m² of sunlight reaching it.
    ground_heating: float


SURFACES = {
    # Asphalt and concrete mixed; asphalt ~0.05-0.10, concrete ~0.25-0.35.
    "paved": Surface(albedo=0.12, ground_heating=0.020),
    "grass": Surface(albedo=0.20, ground_heating=GROUND_HEATING_K_PER_W),
    "field": Surface(albedo=0.20, ground_heating=GROUND_HEATING_K_PER_W),
    "bare": Surface(albedo=0.20, ground_heating=0.015),
    "water": Surface(albedo=0.08, ground_heating=0.005),
    # Forest floor: leaf litter and undergrowth.
    "tree_broadleaf": Surface(albedo=0.15, ground_heating=GROUND_HEATING_K_PER_W),
    "tree_conifer": Surface(albedo=0.15, ground_heating=GROUND_HEATING_K_PER_W),
    "tree_mixed": Surface(albedo=0.15, ground_heating=GROUND_HEATING_K_PER_W),
}
DEFAULT_SURFACE = "paved"


@dataclass(frozen=True)
class Canopy:
    height_m: float
    # Share of direct sunlight that gets through the crown. Measured values
    # for tree shade run 0.18-0.60 against 0.02-0.25 for building shade.
    transmissivity_leaf_on: float
    transmissivity_leaf_off: float

    def transmissivity(self, day: date) -> float:
        return self.transmissivity_leaf_on if in_leaf(day) else self.transmissivity_leaf_off


CANOPIES = {
    "tree_broadleaf": Canopy(height_m=12.0, transmissivity_leaf_on=0.20, transmissivity_leaf_off=0.60),
    "tree_conifer": Canopy(height_m=12.0, transmissivity_leaf_on=0.20, transmissivity_leaf_off=0.20),
    "tree_mixed": Canopy(height_m=12.0, transmissivity_leaf_on=0.20, transmissivity_leaf_off=0.40),
}
# Below this a ray passes under a crown rather than through it.
CROWN_BASE_M = 2.5


@dataclass(frozen=True)
class GroundPatch:
    geometry: BaseGeometry  # projected (EPSG:5179)
    surface: str


@dataclass(frozen=True)
class CanopyPatch:
    geometry: BaseGeometry  # projected (EPSG:5179)
    canopy: Canopy


def load_land_cover(path: Path) -> tuple[list[GroundPatch], list[CanopyPatch]]:
    ground, canopies = [], []
    for feature in json.loads(path.read_text(encoding="utf-8"))["features"]:
        surface = feature["properties"]["surface"]
        geometry = to_projected(shape(feature["geometry"]))
        ground.append(GroundPatch(geometry, surface if surface in SURFACES else DEFAULT_SURFACE))
        if surface in CANOPIES:
            canopies.append(CanopyPatch(geometry, CANOPIES[surface]))
    return ground, canopies
