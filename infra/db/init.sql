CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS buildings (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    geometry geometry(Geometry, 4326) NOT NULL,
    height_m DOUBLE PRECISION NOT NULL CHECK (height_m >= 0),
    source_geometry TEXT NOT NULL,
    source_height TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS buildings_geometry_gix ON buildings USING GIST (geometry);

INSERT INTO buildings (id, name, geometry, height_m, source_geometry, source_height)
VALUES
  (1, 'MVP Building A', ST_GeomFromText('POLYGON((127.45770 36.62625,127.45812 36.62625,127.45812 36.62648,127.45770 36.62648,127.45770 36.62625))', 4326), 18, 'manual-mvp', 'manual-estimate'),
  (2, 'MVP Building B', ST_GeomFromText('POLYGON((127.45835 36.62605,127.45872 36.62605,127.45872 36.62642,127.45835 36.62642,127.45835 36.62605))', 4326), 24, 'manual-mvp', 'manual-estimate'),
  (3, 'MVP Building C', ST_GeomFromText('POLYGON((127.45695 36.62673,127.45743 36.62673,127.45743 36.62695,127.45695 36.62695,127.45695 36.62673))', 4326), 15, 'manual-mvp', 'manual-estimate'),
  (4, 'MVP Building D', ST_GeomFromText('POLYGON((127.45805 36.62678,127.45855 36.62678,127.45855 36.62703,127.45805 36.62703,127.45805 36.62678))', 4326), 30, 'manual-mvp', 'manual-estimate'),
  (5, 'MVP Building E', ST_GeomFromText('POLYGON((127.45900 36.62658,127.45942 36.62658,127.45942 36.62683,127.45900 36.62683,127.45900 36.62658))', 4326), 12, 'manual-mvp', 'manual-estimate'),
  (6, 'MVP Building F', ST_GeomFromText('POLYGON((127.45720 36.62725,127.45768 36.62725,127.45768 36.62748,127.45720 36.62748,127.45720 36.62725))', 4326), 21, 'manual-mvp', 'manual-estimate'),
  (7, 'MVP Building G', ST_GeomFromText('POLYGON((127.45828 36.62732,127.45880 36.62732,127.45880 36.62755,127.45828 36.62755,127.45828 36.62732))', 4326), 27, 'manual-mvp', 'manual-estimate'),
  (8, 'MVP Building H', ST_GeomFromText('POLYGON((127.45908 36.62718,127.45952 36.62718,127.45952 36.62743,127.45908 36.62743,127.45908 36.62718))', 4326), 16, 'manual-mvp', 'manual-estimate')
ON CONFLICT (id) DO NOTHING;

SELECT setval(pg_get_serial_sequence('buildings', 'id'), COALESCE(MAX(id), 1)) FROM buildings;

