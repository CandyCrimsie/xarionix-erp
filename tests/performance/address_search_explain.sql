\set ON_ERROR_STOP on

BEGIN;

CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TEMP TABLE bench_address_objects (
    id bigint PRIMARY KEY,
    parent_id bigint,
    normalized_name text NOT NULL
);

CREATE TEMP TABLE bench_buildings (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    address_object_id bigint NOT NULL,
    normalized_number text NOT NULL,
    normalized_corpus text NOT NULL DEFAULT '',
    normalized_structure text NOT NULL DEFAULT ''
);

CREATE INDEX bench_buildings_normalized_number_idx
    ON bench_buildings (normalized_number);

INSERT INTO bench_address_objects (id, parent_id, normalized_name)
SELECT
    city_id,
    NULL,
    CASE WHEN city_id = 42 THEN 'раменское' ELSE 'город' || city_id END
FROM generate_series(1, 50) AS city_id;

INSERT INTO bench_address_objects (id, parent_id, normalized_name)
SELECT
    100000 + city_id * 1000 + street_id,
    city_id,
    CASE
        WHEN city_id = 42 AND street_id = 42 THEN 'гагарина'
        ELSE 'улица' || street_id
    END
FROM generate_series(1, 50) AS city_id
CROSS JOIN generate_series(1, 100) AS street_id;

INSERT INTO bench_buildings (address_object_id, normalized_number)
SELECT
    object_id,
    number::text
FROM (
    SELECT 100000 + city_id * 1000 + street_id AS object_id
    FROM generate_series(1, 50) AS city_id
    CROSS JOIN generate_series(1, 100) AS street_id
) AS streets
CROSS JOIN (
    SELECT number FROM generate_series(50, 69) AS number
    UNION ALL
    SELECT 153
) AS numbers;

ANALYZE bench_address_objects;
ANALYZE bench_buildings;

\echo 'OLD contains-only search (also admits house 153 for token 53)'
EXPLAIN (ANALYZE, BUFFERS)
WITH RECURSIVE address_paths AS (
    SELECT
        id AS object_id,
        normalized_name AS normalized_path
    FROM bench_address_objects
    WHERE parent_id IS NULL

    UNION ALL

    SELECT
        child.id,
        parent.normalized_path || ' ' || child.normalized_name
    FROM bench_address_objects AS child
    JOIN address_paths AS parent ON child.parent_id = parent.object_id
)
SELECT building.id
FROM bench_buildings AS building
JOIN address_paths AS path ON path.object_id = building.address_object_id
WHERE concat(
    path.normalized_path,
    ' ',
    building.normalized_number,
    ' дом ',
    building.normalized_corpus,
    ' корпус ',
    building.normalized_structure,
    ' строение'
) LIKE '%рам%'
AND concat(
    path.normalized_path,
    ' ',
    building.normalized_number,
    ' дом ',
    building.normalized_corpus,
    ' корпус ',
    building.normalized_structure,
    ' строение'
) LIKE '%гагар%'
AND concat(
    path.normalized_path,
    ' ',
    building.normalized_number,
    ' дом ',
    building.normalized_corpus,
    ' корпус ',
    building.normalized_structure,
    ' строение'
) LIKE '%53%'
ORDER BY path.normalized_path, building.normalized_number, building.id
LIMIT 20;

\echo 'NEW structured/ranked search (exact house number plus bounded fuzzy names)'
EXPLAIN (ANALYZE, BUFFERS)
WITH RECURSIVE address_paths AS (
    SELECT
        id AS object_id,
        normalized_name AS normalized_path,
        normalized_name AS normalized_leaf_name
    FROM bench_address_objects
    WHERE parent_id IS NULL

    UNION ALL

    SELECT
        child.id,
        parent.normalized_path || ' ' || child.normalized_name,
        child.normalized_name
    FROM bench_address_objects AS child
    JOIN address_paths AS parent ON child.parent_id = parent.object_id
)
SELECT building.id
FROM bench_buildings AS building
JOIN address_paths AS path ON path.object_id = building.address_object_id
WHERE building.normalized_number = '53'
AND (
    path.normalized_path LIKE '%рам%'
)
AND (
    path.normalized_path LIKE '%гагар%'
    OR word_similarity('гагар', path.normalized_path) >= 0.55
)
ORDER BY
    (
        CASE
            WHEN path.normalized_leaf_name = 'рам' THEN 50
            WHEN path.normalized_path ~ '(^| )рам($| )' THEN 40
            WHEN path.normalized_leaf_name LIKE 'рам%' THEN 30
            WHEN path.normalized_path ~ '(^| )рам' THEN 24
            WHEN path.normalized_path LIKE '%рам%' THEN 10
            ELSE 0
        END
        +
        CASE
            WHEN path.normalized_leaf_name = 'гагар' THEN 50
            WHEN path.normalized_path ~ '(^| )гагар($| )' THEN 40
            WHEN path.normalized_leaf_name LIKE 'гагар%' THEN 30
            WHEN path.normalized_path ~ '(^| )гагар' THEN 24
            WHEN path.normalized_path LIKE '%гагар%' THEN 10
            ELSE word_similarity('гагар', path.normalized_path) * 8
        END
        + 120
    ) DESC,
    path.normalized_path,
    building.normalized_number,
    building.id
LIMIT 20;

ROLLBACK;
