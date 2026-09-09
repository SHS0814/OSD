import json
from pathlib import Path

import geopandas as gpd
import psycopg
from shapely import wkb

from app.models.building import Building


class BuildingRepository:
    def __init__(self, database_url: str | None, sample_path: Path):
        self.database_url = database_url
        self.sample_path = sample_path

    def list_buildings(self) -> list[Building]:
        if self.database_url:
            return self._from_postgis()
        return self._from_geojson()

    def _from_postgis(self) -> list[Building]:
        query = """
            SELECT id, name, ST_AsBinary(geometry), height_m,
                   source_geometry, source_height
            FROM buildings
            ORDER BY id
        """
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(query)
                return [
                    Building(
                        id=row[0],
                        name=row[1],
                        geometry=wkb.loads(bytes(row[2])),
                        height_m=float(row[3]),
                        source_geometry=row[4],
                        source_height=row[5],
                    )
                    for row in cursor.fetchall()
                ]

    def _from_geojson(self) -> list[Building]:
        collection = json.loads(self.sample_path.read_text(encoding="utf-8"))
        frame = gpd.GeoDataFrame.from_features(
            collection["features"],
            crs="EPSG:4326",
        )
        return [
            Building(
                id=int(row.id),
                name=row.name,
                geometry=row.geometry,
                height_m=float(row.height_m),
                source_geometry=row.source_geometry,
                source_height=row.source_height,
            )
            for row in frame.itertuples(index=False)
        ]
