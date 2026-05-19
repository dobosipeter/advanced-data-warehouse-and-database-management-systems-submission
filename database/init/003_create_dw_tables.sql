CREATE TABLE IF NOT EXISTS dw.dim_date (
    date_key INTEGER PRIMARY KEY,
    full_date DATE NOT NULL UNIQUE,
    year SMALLINT NOT NULL,
    quarter SMALLINT NOT NULL CHECK (quarter BETWEEN 1 AND 4),
    month SMALLINT NOT NULL CHECK (month BETWEEN 1 AND 12),
    day SMALLINT NOT NULL CHECK (day BETWEEN 1 AND 31),
    day_name TEXT NOT NULL,
    weekday SMALLINT NOT NULL CHECK (weekday BETWEEN 1 AND 7),
    is_weekend BOOLEAN NOT NULL
);

CREATE TABLE IF NOT EXISTS dw.dim_time (
    time_key INTEGER PRIMARY KEY,
    hour SMALLINT NOT NULL CHECK (hour BETWEEN 0 AND 23),
    minute SMALLINT NOT NULL CHECK (minute BETWEEN 0 AND 59),
    part_of_day TEXT NOT NULL CHECK (part_of_day IN ('night', 'morning', 'afternoon', 'evening'))
);

CREATE TABLE IF NOT EXISTS dw.dim_parameter (
    parameter_key BIGSERIAL PRIMARY KEY,
    source_parameter_id BIGINT,
    code TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    unit TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT true
);

CREATE TABLE IF NOT EXISTS dw.dim_location (
    location_key BIGSERIAL PRIMARY KEY,
    source_location_id BIGINT NOT NULL,
    openaq_location_id BIGINT NOT NULL,
    name TEXT NOT NULL,
    city TEXT NOT NULL,
    country TEXT NOT NULL,
    latitude NUMERIC(9, 6),
    longitude NUMERIC(9, 6),
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ,
    is_current BOOLEAN NOT NULL DEFAULT true,
    row_hash TEXT NOT NULL,
    CONSTRAINT dim_location_valid_range CHECK (valid_to IS NULL OR valid_to > valid_from)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_dw_dim_location_current_source
    ON dw.dim_location (source_location_id)
    WHERE is_current;

CREATE UNIQUE INDEX IF NOT EXISTS ux_dw_dim_location_source_valid_from
    ON dw.dim_location (source_location_id, valid_from);

CREATE TABLE IF NOT EXISTS dw.dim_sensor (
    sensor_key BIGSERIAL PRIMARY KEY,
    source_sensor_id BIGINT NOT NULL,
    openaq_sensor_id BIGINT NOT NULL,
    source_location_id BIGINT NOT NULL,
    source_parameter_id BIGINT NOT NULL,
    unit TEXT NOT NULL,
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ,
    is_current BOOLEAN NOT NULL DEFAULT true,
    row_hash TEXT NOT NULL,
    CONSTRAINT dim_sensor_valid_range CHECK (valid_to IS NULL OR valid_to > valid_from)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_dw_dim_sensor_current_source
    ON dw.dim_sensor (source_sensor_id)
    WHERE is_current;

CREATE UNIQUE INDEX IF NOT EXISTS ux_dw_dim_sensor_source_valid_from
    ON dw.dim_sensor (source_sensor_id, valid_from);

CREATE TABLE IF NOT EXISTS dw.dim_risk_class (
    risk_class_key SMALLSERIAL PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    label TEXT NOT NULL,
    min_value NUMERIC(12, 4) NOT NULL CHECK (min_value >= 0),
    max_value NUMERIC(12, 4),
    sort_order SMALLINT NOT NULL UNIQUE,
    CONSTRAINT dim_risk_class_range CHECK (max_value IS NULL OR max_value > min_value)
);

CREATE TABLE IF NOT EXISTS dw.fact_air_quality_measurement (
    fact_measurement_id BIGSERIAL PRIMARY KEY,
    source_measurement_id BIGINT NOT NULL UNIQUE,
    location_key BIGINT NOT NULL REFERENCES dw.dim_location(location_key),
    sensor_key BIGINT NOT NULL REFERENCES dw.dim_sensor(sensor_key),
    parameter_key BIGINT NOT NULL REFERENCES dw.dim_parameter(parameter_key),
    date_key INTEGER NOT NULL REFERENCES dw.dim_date(date_key),
    time_key INTEGER NOT NULL REFERENCES dw.dim_time(time_key),
    risk_class_key SMALLINT REFERENCES dw.dim_risk_class(risk_class_key),
    measured_at TIMESTAMPTZ NOT NULL,
    measurement_value NUMERIC(12, 4) NOT NULL,
    unit TEXT NOT NULL,
    ingestion_run_id BIGINT,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS dw.fact_pollution_alert (
    fact_alert_id BIGSERIAL PRIMARY KEY,
    source_alert_id BIGINT NOT NULL UNIQUE,
    location_key BIGINT NOT NULL REFERENCES dw.dim_location(location_key),
    parameter_key BIGINT NOT NULL REFERENCES dw.dim_parameter(parameter_key),
    risk_class_key SMALLINT REFERENCES dw.dim_risk_class(risk_class_key),
    date_key INTEGER NOT NULL REFERENCES dw.dim_date(date_key),
    time_key INTEGER NOT NULL REFERENCES dw.dim_time(time_key),
    alert_level TEXT NOT NULL,
    alert_status TEXT NOT NULL,
    measurement_value NUMERIC(12, 4) NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS dw.fact_prediction (
    fact_prediction_id BIGSERIAL PRIMARY KEY,
    location_key BIGINT NOT NULL REFERENCES dw.dim_location(location_key),
    sensor_key BIGINT REFERENCES dw.dim_sensor(sensor_key),
    parameter_key BIGINT NOT NULL REFERENCES dw.dim_parameter(parameter_key),
    target_date_key INTEGER NOT NULL REFERENCES dw.dim_date(date_key),
    target_time_key INTEGER NOT NULL REFERENCES dw.dim_time(time_key),
    target_measured_at TIMESTAMPTZ NOT NULL,
    prediction_created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    predicted_value NUMERIC(12, 4) NOT NULL,
    risk_class_key SMALLINT REFERENCES dw.dim_risk_class(risk_class_key),
    model_name TEXT NOT NULL,
    model_version TEXT NOT NULL,
    feature_payload JSONB
);

INSERT INTO dw.dim_date (date_key, full_date, year, quarter, month, day, day_name, weekday, is_weekend)
SELECT
    to_char(day_value, 'YYYYMMDD')::integer AS date_key,
    day_value AS full_date,
    EXTRACT(YEAR FROM day_value)::smallint AS year,
    EXTRACT(QUARTER FROM day_value)::smallint AS quarter,
    EXTRACT(MONTH FROM day_value)::smallint AS month,
    EXTRACT(DAY FROM day_value)::smallint AS day,
    to_char(day_value, 'FMDay') AS day_name,
    EXTRACT(ISODOW FROM day_value)::smallint AS weekday,
    EXTRACT(ISODOW FROM day_value) IN (6, 7) AS is_weekend
FROM generate_series(DATE '2024-01-01', DATE '2026-12-31', INTERVAL '1 day') AS generated(day_value)
ON CONFLICT (date_key) DO UPDATE
SET
    full_date = EXCLUDED.full_date,
    year = EXCLUDED.year,
    quarter = EXCLUDED.quarter,
    month = EXCLUDED.month,
    day = EXCLUDED.day,
    day_name = EXCLUDED.day_name,
    weekday = EXCLUDED.weekday,
    is_weekend = EXCLUDED.is_weekend;

INSERT INTO dw.dim_time (time_key, hour, minute, part_of_day)
SELECT
    (hour_value * 100 + minute_value)::integer AS time_key,
    hour_value::smallint AS hour,
    minute_value::smallint AS minute,
    CASE
        WHEN hour_value BETWEEN 0 AND 5 THEN 'night'
        WHEN hour_value BETWEEN 6 AND 11 THEN 'morning'
        WHEN hour_value BETWEEN 12 AND 17 THEN 'afternoon'
        ELSE 'evening'
    END AS part_of_day
FROM generate_series(0, 23) AS hours(hour_value)
CROSS JOIN generate_series(0, 59) AS minutes(minute_value)
ON CONFLICT (time_key) DO UPDATE
SET
    hour = EXCLUDED.hour,
    minute = EXCLUDED.minute,
    part_of_day = EXCLUDED.part_of_day;

INSERT INTO dw.dim_risk_class (code, label, min_value, max_value, sort_order)
VALUES
    ('low', 'Low', 0, 10, 1),
    ('moderate', 'Moderate', 10, 25, 2),
    ('high', 'High', 25, 50, 3),
    ('critical', 'Critical', 50, NULL, 4)
ON CONFLICT (code) DO UPDATE
SET
    label = EXCLUDED.label,
    min_value = EXCLUDED.min_value,
    max_value = EXCLUDED.max_value,
    sort_order = EXCLUDED.sort_order;
