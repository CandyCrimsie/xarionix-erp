\set ON_ERROR_STOP on

BEGIN;

CREATE TEMP TABLE bench_map_buildings (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    latitude numeric(10, 7),
    longitude numeric(10, 7)
);

INSERT INTO bench_map_buildings (latitude, longitude)
SELECT
    40 + ((value::bigint * 1543) % 300000)::numeric / 10000,
    20 + ((value::bigint * 7919) % 1400000)::numeric / 10000
FROM generate_series(1, 500000) AS value;

INSERT INTO bench_map_buildings (latitude, longitude)
SELECT NULL, NULL
FROM generate_series(1, 50000);

ANALYZE bench_map_buildings;

\echo 'BBOX without a coordinate index'
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, latitude, longitude
FROM bench_map_buildings
WHERE longitude BETWEEN 37.60 AND 37.70
  AND latitude BETWEEN 55.70 AND 55.80
ORDER BY id
LIMIT 2001;

CREATE INDEX bench_map_coordinates_idx
    ON bench_map_buildings (longitude, latitude)
    WHERE longitude IS NOT NULL AND latitude IS NOT NULL;

ANALYZE bench_map_buildings;

\echo 'BBOX with the production-shaped partial coordinate index'
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, latitude, longitude
FROM bench_map_buildings
WHERE longitude BETWEEN 37.60 AND 37.70
  AND latitude BETWEEN 55.70 AND 55.80
ORDER BY id
LIMIT 2001;

ROLLBACK;
