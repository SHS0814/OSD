from dataclasses import dataclass
from typing import Any

from shapely.geometry.base import BaseGeometry


@dataclass(frozen=True)
class Building:
    id: int
    name: str
    geometry: BaseGeometry
    height_m: float | None
    source_geometry: str
    source_height: str | None
    osm_type: str
    osm_id: int
    vworld_id: str | None

    def properties(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "height_m": self.height_m,
            "source_geometry": self.source_geometry,
            "source_height": self.source_height,
            "osm_type": self.osm_type,
            "osm_id": self.osm_id,
            "vworld_id": self.vworld_id,
        }
