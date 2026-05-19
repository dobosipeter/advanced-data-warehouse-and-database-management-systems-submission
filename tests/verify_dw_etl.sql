DO $$
DECLARE
    source_measurements INTEGER;
    fact_measurements INTEGER;
    missing_dimension_count INTEGER;
BEGIN
    SELECT count(*) INTO source_measurements FROM oltp.measurement_raw;
    SELECT count(*) INTO fact_measurements FROM dw.fact_air_quality_measurement;

    IF source_measurements > 0 AND fact_measurements = 0 THEN
        RAISE EXCEPTION 'Expected DW measurement facts after ETL';
    END IF;

    SELECT count(*)
    INTO missing_dimension_count
    FROM dw.fact_air_quality_measurement AS f
    LEFT JOIN dw.dim_location AS dl ON dl.location_key = f.location_key
    LEFT JOIN dw.dim_sensor AS ds ON ds.sensor_key = f.sensor_key
    LEFT JOIN dw.dim_parameter AS dp ON dp.parameter_key = f.parameter_key
    LEFT JOIN dw.dim_date AS dd ON dd.date_key = f.date_key
    LEFT JOIN dw.dim_time AS dt ON dt.time_key = f.time_key
    WHERE dl.location_key IS NULL
       OR ds.sensor_key IS NULL
       OR dp.parameter_key IS NULL
       OR dd.date_key IS NULL
       OR dt.time_key IS NULL;

    IF missing_dimension_count <> 0 THEN
        RAISE EXCEPTION 'Found facts with missing dimension keys: %', missing_dimension_count;
    END IF;

    IF EXISTS (
        SELECT source_measurement_id
        FROM dw.fact_air_quality_measurement
        GROUP BY source_measurement_id
        HAVING count(*) > 1
    ) THEN
        RAISE EXCEPTION 'Expected measurement fact load to be idempotent';
    END IF;
END $$;
