from dataclasses import dataclass
from typing import Any

from shapely.geometry.base import BaseGeometry


@dataclass(frozen=True)
class Building:
    id: int
    name: str
    geometry: BaseGeometry
    height_m: float
    source_geometry: str
    source_height: str

    def properties(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "height_m": self.height_m,
            "source_geometry": self.source_geometry,
            "source_height": self.source_height,
        }

