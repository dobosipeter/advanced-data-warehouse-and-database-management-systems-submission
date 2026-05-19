DO $$
DECLARE
    date_count INTEGER;
    time_count INTEGER;
    risk_count INTEGER;
    missing_table_count INTEGER;
BEGIN
    SELECT count(*)
    INTO missing_table_count
    FROM (
        VALUES
            ('dim_date'),
            ('dim_time'),
            ('dim_parameter'),
            ('dim_location'),
            ('dim_sensor'),
            ('dim_risk_class'),
            ('fact_air_quality_measurement'),
            ('fact_pollution_alert'),
            ('fact_prediction')
    ) AS expected(table_name)
    WHERE NOT EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'dw'
          AND table_name = expected.table_name
    );

    IF missing_table_count <> 0 THEN
        RAISE EXCEPTION 'Expected all DW tables to exist; missing count=%', missing_table_count;
    END IF;

    SELECT count(*) INTO date_count FROM dw.dim_date;
    IF date_count <> 1096 THEN
        RAISE EXCEPTION 'Expected 1096 dim_date rows for 2024-01-01..2026-12-31, found %', date_count;
    END IF;

    SELECT count(*) INTO time_count FROM dw.dim_time;
    IF time_count <> 1440 THEN
        RAISE EXCEPTION 'Expected 1440 dim_time minute rows, found %', time_count;
    END IF;

    SELECT count(*) INTO risk_count FROM dw.dim_risk_class;
    IF risk_count <> 4 THEN
        RAISE EXCEPTION 'Expected 4 risk classes, found %', risk_count;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_indexes
        WHERE schemaname = 'dw'
          AND indexname = 'ux_dw_dim_location_current_source'
    ) THEN
        RAISE EXCEPTION 'Expected current-location SCD2 unique index';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_indexes
        WHERE schemaname = 'dw'
          AND indexname = 'ux_dw_dim_sensor_current_source'
    ) THEN
        RAISE EXCEPTION 'Expected current-sensor SCD2 unique index';
    END IF;
END $$;
