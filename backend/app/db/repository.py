import json
from pathlib import Path

import geopandas as gpd
import pandas as pd
import psycopg
from shapely import wkb
from shapely.geometry import mapping

from app.models.building import Building


class BuildingRepository:
    def __init__(self, database_url: str | None, snapshot_path: Path):
        self.database_url = database_url
        self.snapshot_path = snapshot_path

    def synchronize_snapshot(self) -> None:
        """Idempotently make PostGIS reflect the committed building snapshot."""
        if not self.database_url:
            return
        records = self._from_geojson()
        osm_ids = [record.osm_id for record in records]
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                self._migrate_schema(cursor)
                cursor.execute(
                    "DELETE FROM buildings WHERE source_geometry = 'manual-mvp'"
                )
                for record in records:
                    cursor.execute(
                        """
                        INSERT INTO buildings (
                            id, name, geometry, height_m, source_geometry,
                            source_height, osm_type, osm_id, vworld_id, updated_at
                        ) VALUES (
                            %s, %s, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326), %s,
                            %s, %s, %s, %s, %s, now()
                        )
                        ON CONFLICT (id) DO UPDATE SET
                            name = EXCLUDED.name,
                            geometry = EXCLUDED.geometry,
                            height_m = EXCLUDED.height_m,
                            source_geometry = EXCLUDED.source_geometry,
                            source_height = EXCLUDED.source_height,
                            osm_type = EXCLUDED.osm_type,
                            osm_id = EXCLUDED.osm_id,
                            vworld_id = EXCLUDED.vworld_id,
                            updated_at = now()
                        """,
                        (
                            record.id,
                            record.name,
                            json.dumps(mapping(record.geometry)),
                            record.height_m,
                            record.source_geometry,
                            record.source_height,
                            record.osm_type,
                            record.osm_id,
                            record.vworld_id,
                        ),
                    )
                cursor.execute(
                    """
                    DELETE FROM buildings
                    WHERE source_geometry = 'OpenStreetMap'
                      AND NOT (osm_id = ANY(%s))
                    """,
                    (osm_ids,),
                )

    @staticmethod
    def _migrate_schema(cursor: psycopg.Cursor) -> None:
        cursor.execute("ALTER TABLE buildings ALTER COLUMN height_m DROP NOT NULL")
        cursor.execute("ALTER TABLE buildings ALTER COLUMN source_height DROP NOT NULL")
        cursor.execute("ALTER TABLE buildings ADD COLUMN IF NOT EXISTS osm_type TEXT")
        cursor.execute("ALTER TABLE buildings ADD COLUMN IF NOT EXISTS osm_id BIGINT")
        cursor.execute("ALTER TABLE buildings ADD COLUMN IF NOT EXISTS vworld_id TEXT")
        cursor.execute(
            "ALTER TABLE buildings ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now()"
        )
        cursor.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS buildings_osm_identity_idx ON buildings (osm_type, osm_id)"
        )

    def list_buildings(self) -> list[Building]:
        if self.database_url:
            return self._from_postgis()
        return self._from_geojson()

    def _from_postgis(self) -> list[Building]:
        query = """
            SELECT id, name, ST_AsBinary(geometry), height_m,
                   source_geometry, source_height, osm_type, osm_id, vworld_id
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
                        height_m=float(row[3]) if row[3] is not None else None,
                        source_geometry=row[4],
                        source_height=row[5],
                        osm_type=row[6],
                        osm_id=int(row[7]),
                        vworld_id=row[8],
                    )
                    for row in cursor.fetchall()
                ]

    def _from_geojson(self) -> list[Building]:
        collection = json.loads(self.snapshot_path.read_text(encoding="utf-8"))
        frame = gpd.GeoDataFrame.from_features(
            collection["features"],
            crs="EPSG:4326",
        )
        return [
            Building(
                id=int(row.id),
                name=row.name,
                geometry=row.geometry,
                height_m=None if pd.isna(row.height_m) else float(row.height_m),
                source_geometry=row.source_geometry,
                source_height=None if pd.isna(row.source_height) else row.source_height,
                osm_type=getattr(row, "osm_type", "legacy"),
                osm_id=int(getattr(row, "osm_id", row.id)),
                vworld_id=(
                    None
                    if pd.isna(getattr(row, "vworld_id", None))
                    else str(row.vworld_id)
                ),
            )
            for row in frame.itertuples(index=False)
        ]
