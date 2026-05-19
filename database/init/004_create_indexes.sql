CREATE INDEX IF NOT EXISTS idx_staging_raw_api_response_run
    ON staging.raw_api_response (ingestion_run_id);

CREATE INDEX IF NOT EXISTS idx_staging_raw_api_response_body_gin
    ON staging.raw_api_response USING GIN (response_body);

CREATE INDEX IF NOT EXISTS idx_oltp_location_city
    ON oltp.location (city);

CREATE INDEX IF NOT EXISTS idx_oltp_sensor_location
    ON oltp.sensor (location_id);

CREATE INDEX IF NOT EXISTS idx_oltp_sensor_parameter
    ON oltp.sensor (parameter_id);

CREATE INDEX IF NOT EXISTS idx_oltp_measurement_measured_at_brin
    ON oltp.measurement_raw USING BRIN (measured_at);

CREATE INDEX IF NOT EXISTS idx_oltp_measurement_run
    ON oltp.measurement_raw (ingestion_run_id);

CREATE INDEX IF NOT EXISTS idx_oltp_measurement_sensor
    ON oltp.measurement_raw (sensor_id);

CREATE INDEX IF NOT EXISTS idx_oltp_measurement_time_sensor
    ON oltp.measurement_raw (measured_at DESC, sensor_id);

CREATE INDEX IF NOT EXISTS idx_oltp_threshold_rule_active
    ON oltp.threshold_rule (parameter_id, city)
    WHERE is_active;

CREATE INDEX IF NOT EXISTS idx_oltp_pollution_alert_status
    ON oltp.pollution_alert (status, generated_at DESC);

CREATE INDEX IF NOT EXISTS idx_dw_dim_location_current
    ON dw.dim_location (source_location_id)
    WHERE is_current;

CREATE INDEX IF NOT EXISTS idx_dw_dim_sensor_current
    ON dw.dim_sensor (source_sensor_id)
    WHERE is_current;

CREATE INDEX IF NOT EXISTS idx_dw_fact_measurement_date_parameter
    ON dw.fact_air_quality_measurement (date_key, parameter_key);

CREATE INDEX IF NOT EXISTS idx_dw_fact_measurement_measured_at_brin
    ON dw.fact_air_quality_measurement USING BRIN (measured_at);

CREATE INDEX IF NOT EXISTS idx_dw_fact_alert_date_level
    ON dw.fact_pollution_alert (date_key, alert_level);

CREATE INDEX IF NOT EXISTS idx_dw_fact_prediction_target
    ON dw.fact_prediction (target_date_key, target_time_key, parameter_key);
