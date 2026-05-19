DO $$
DECLARE
    bad_location_current_count INTEGER;
    bad_sensor_current_count INTEGER;
    historical_fact_count INTEGER;
BEGIN
    SELECT count(*)
    INTO bad_location_current_count
    FROM (
        SELECT source_location_id
        FROM dw.dim_location
        WHERE is_current
        GROUP BY source_location_id
        HAVING count(*) <> 1
    ) AS bad_locations;

    IF bad_location_current_count <> 0 THEN
        RAISE EXCEPTION 'Expected exactly one current dim_location row per source location';
    END IF;

    SELECT count(*)
    INTO bad_sensor_current_count
    FROM (
        SELECT source_sensor_id
        FROM dw.dim_sensor
        WHERE is_current
        GROUP BY source_sensor_id
        HAVING count(*) <> 1
    ) AS bad_sensors;

    IF bad_sensor_current_count <> 0 THEN
        RAISE EXCEPTION 'Expected exactly one current dim_sensor row per source sensor';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM dw.dim_location
        WHERE NOT is_current
          AND valid_to IS NULL
    ) THEN
        RAISE EXCEPTION 'Expected expired location versions to have valid_to set';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM dw.dim_sensor
        WHERE NOT is_current
          AND valid_to IS NULL
    ) THEN
        RAISE EXCEPTION 'Expected expired sensor versions to have valid_to set';
    END IF;

    SELECT count(*)
    INTO historical_fact_count
    FROM dw.fact_air_quality_measurement AS f
    JOIN dw.dim_location AS dl
        ON dl.location_key = f.location_key
    WHERE NOT dl.is_current;

    IF historical_fact_count = 0 THEN
        RAISE EXCEPTION 'Expected at least one fact to remain attached to a historical location version after SCD2 simulation';
    END IF;
END $$;
