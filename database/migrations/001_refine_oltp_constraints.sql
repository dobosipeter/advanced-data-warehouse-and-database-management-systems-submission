DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ingestion_run_finished_after_started') THEN
        ALTER TABLE oltp.ingestion_run_log
            ADD CONSTRAINT ingestion_run_finished_after_started CHECK (finished_at IS NULL OR finished_at >= started_at);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'parameter_code_not_blank') THEN
        ALTER TABLE oltp.parameter
            ADD CONSTRAINT parameter_code_not_blank CHECK (btrim(code) <> '');
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'parameter_display_name_not_blank') THEN
        ALTER TABLE oltp.parameter
            ADD CONSTRAINT parameter_display_name_not_blank CHECK (btrim(display_name) <> '');
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'parameter_unit_not_blank') THEN
        ALTER TABLE oltp.parameter
            ADD CONSTRAINT parameter_unit_not_blank CHECK (btrim(preferred_unit) <> '');
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'location_name_not_blank') THEN
        ALTER TABLE oltp.location
            ADD CONSTRAINT location_name_not_blank CHECK (btrim(name) <> '');
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'location_city_not_blank') THEN
        ALTER TABLE oltp.location
            ADD CONSTRAINT location_city_not_blank CHECK (btrim(city) <> '');
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'location_country_not_blank') THEN
        ALTER TABLE oltp.location
            ADD CONSTRAINT location_country_not_blank CHECK (btrim(country) <> '');
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'location_seen_range') THEN
        ALTER TABLE oltp.location
            ADD CONSTRAINT location_seen_range CHECK (last_seen_at >= first_seen_at);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'sensor_unit_not_blank') THEN
        ALTER TABLE oltp.sensor
            ADD CONSTRAINT sensor_unit_not_blank CHECK (btrim(unit) <> '');
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'sensor_seen_range') THEN
        ALTER TABLE oltp.sensor
            ADD CONSTRAINT sensor_seen_range CHECK (last_seen_at >= first_seen_at);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'measurement_unit_not_blank') THEN
        ALTER TABLE oltp.measurement_raw
            ADD CONSTRAINT measurement_unit_not_blank CHECK (btrim(unit) <> '');
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'threshold_rule_city_not_blank') THEN
        ALTER TABLE oltp.threshold_rule
            ADD CONSTRAINT threshold_rule_city_not_blank CHECK (btrim(city) <> '');
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'pollution_alert_reviewed_after_generated') THEN
        ALTER TABLE oltp.pollution_alert
            ADD CONSTRAINT pollution_alert_reviewed_after_generated CHECK (reviewed_at IS NULL OR reviewed_at >= generated_at);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'raw_api_response_endpoint_not_blank') THEN
        ALTER TABLE staging.raw_api_response
            ADD CONSTRAINT raw_api_response_endpoint_not_blank CHECK (btrim(source_endpoint) <> '');
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'raw_api_response_url_not_blank') THEN
        ALTER TABLE staging.raw_api_response
            ADD CONSTRAINT raw_api_response_url_not_blank CHECK (btrim(request_url) <> '');
    END IF;
END $$;
