CREATE TABLE IF NOT EXISTS oltp.ingestion_run_log (
    ingestion_run_id BIGSERIAL PRIMARY KEY,
    run_type TEXT NOT NULL CHECK (run_type IN ('initial', 'incremental', 'manual')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'succeeded', 'failed', 'partial')),
    records_requested INTEGER NOT NULL DEFAULT 0 CHECK (records_requested >= 0),
    records_inserted INTEGER NOT NULL DEFAULT 0 CHECK (records_inserted >= 0),
    records_failed INTEGER NOT NULL DEFAULT 0 CHECK (records_failed >= 0),
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS oltp.parameter (
    parameter_id BIGSERIAL PRIMARY KEY,
    openaq_parameter_id BIGINT UNIQUE,
    code TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    description TEXT,
    preferred_unit TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS oltp.location (
    location_id BIGSERIAL PRIMARY KEY,
    openaq_location_id BIGINT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    city TEXT NOT NULL,
    country TEXT NOT NULL,
    latitude NUMERIC(9, 6),
    longitude NUMERIC(9, 6),
    timezone TEXT,
    is_active BOOLEAN NOT NULL DEFAULT true,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    raw_payload JSONB,
    CONSTRAINT location_latitude_range CHECK (latitude IS NULL OR latitude BETWEEN -90 AND 90),
    CONSTRAINT location_longitude_range CHECK (longitude IS NULL OR longitude BETWEEN -180 AND 180)
);

CREATE TABLE IF NOT EXISTS oltp.sensor (
    sensor_id BIGSERIAL PRIMARY KEY,
    openaq_sensor_id BIGINT NOT NULL UNIQUE,
    location_id BIGINT NOT NULL REFERENCES oltp.location(location_id),
    parameter_id BIGINT NOT NULL REFERENCES oltp.parameter(parameter_id),
    unit TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT true,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    raw_payload JSONB
);

CREATE TABLE IF NOT EXISTS oltp.measurement_raw (
    measurement_id BIGSERIAL PRIMARY KEY,
    sensor_id BIGINT NOT NULL REFERENCES oltp.sensor(sensor_id),
    measured_at TIMESTAMPTZ NOT NULL,
    value NUMERIC(12, 4) NOT NULL,
    unit TEXT NOT NULL,
    ingestion_run_id BIGINT REFERENCES oltp.ingestion_run_log(ingestion_run_id),
    raw_payload JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT measurement_value_reasonable CHECK (value > -1000 AND value < 100000)
);

CREATE TABLE IF NOT EXISTS oltp.threshold_rule (
    threshold_rule_id BIGSERIAL PRIMARY KEY,
    parameter_id BIGINT NOT NULL REFERENCES oltp.parameter(parameter_id),
    city TEXT NOT NULL,
    warning_level TEXT NOT NULL CHECK (warning_level IN ('low', 'moderate', 'high', 'critical')),
    min_value NUMERIC(12, 4) NOT NULL CHECK (min_value >= 0),
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (parameter_id, city, warning_level)
);

CREATE TABLE IF NOT EXISTS oltp.pollution_alert (
    pollution_alert_id BIGSERIAL PRIMARY KEY,
    measurement_id BIGINT NOT NULL REFERENCES oltp.measurement_raw(measurement_id),
    threshold_rule_id BIGINT NOT NULL REFERENCES oltp.threshold_rule(threshold_rule_id),
    alert_level TEXT NOT NULL CHECK (alert_level IN ('low', 'moderate', 'high', 'critical')),
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'reviewed', 'closed')),
    generated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    reviewed_at TIMESTAMPTZ,
    notes TEXT,
    UNIQUE (measurement_id, threshold_rule_id)
);

CREATE TABLE IF NOT EXISTS staging.raw_api_response (
    raw_api_response_id BIGSERIAL PRIMARY KEY,
    ingestion_run_id BIGINT REFERENCES oltp.ingestion_run_log(ingestion_run_id),
    source_endpoint TEXT NOT NULL,
    request_url TEXT NOT NULL,
    request_params JSONB,
    response_body JSONB NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
