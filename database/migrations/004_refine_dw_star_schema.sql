BEGIN;

CREATE UNIQUE INDEX IF NOT EXISTS ux_dw_dim_location_current_source
    ON dw.dim_location (source_location_id)
    WHERE is_current;

CREATE UNIQUE INDEX IF NOT EXISTS ux_dw_dim_location_source_valid_from
    ON dw.dim_location (source_location_id, valid_from);

CREATE UNIQUE INDEX IF NOT EXISTS ux_dw_dim_sensor_current_source
    ON dw.dim_sensor (source_sensor_id)
    WHERE is_current;

CREATE UNIQUE INDEX IF NOT EXISTS ux_dw_dim_sensor_source_valid_from
    ON dw.dim_sensor (source_sensor_id, valid_from);

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

COMMIT;
