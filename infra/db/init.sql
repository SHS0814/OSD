CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS buildings (
    id BIGINT PRIMARY KEY,
    name TEXT NOT NULL,
    geometry geometry(Geometry, 4326) NOT NULL,
    height_m DOUBLE PRECISION CHECK (height_m >= 0),
    source_geometry TEXT NOT NULL,
    source_height TEXT,
    osm_type TEXT,
    osm_id BIGINT,
    vworld_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS buildings_geometry_gix ON buildings USING GIST (geometry);
CREATE UNIQUE INDEX IF NOT EXISTS buildings_osm_identity_idx ON buildings (osm_type, osm_id);
