BEGIN;

INSERT INTO oltp.ingestion_run_log (run_type, status)
VALUES ('manual', 'succeeded')
RETURNING ingestion_run_id \gset verify_

INSERT INTO oltp.parameter (openaq_parameter_id, code, display_name, preferred_unit)
VALUES (-9001, 'verify_pm25', 'Verify PM2.5', 'ug/m3')
RETURNING parameter_id \gset verify_

INSERT INTO oltp.location (openaq_location_id, name, city, country, latitude, longitude, timezone)
VALUES (-9001, 'Verify Station', 'Budapest', 'HU', 47.4979, 19.0402, 'Europe/Budapest')
RETURNING location_id \gset verify_

INSERT INTO oltp.sensor (openaq_sensor_id, location_id, parameter_id, unit)
VALUES (-9001, :verify_location_id, :verify_parameter_id, 'ug/m3')
RETURNING sensor_id \gset verify_

INSERT INTO oltp.measurement_raw (sensor_id, measured_at, value, unit, ingestion_run_id)
VALUES (:verify_sensor_id, '2026-01-01T00:00:00Z', 12.3400, 'ug/m3', :verify_ingestion_run_id)
RETURNING measurement_id \gset verify_

INSERT INTO oltp.threshold_rule (parameter_id, city, warning_level, min_value)
VALUES (:verify_parameter_id, 'Budapest', 'moderate', 10.0000)
RETURNING threshold_rule_id \gset verify_

INSERT INTO oltp.pollution_alert (measurement_id, threshold_rule_id, alert_level, status)
VALUES (:verify_measurement_id, :verify_threshold_rule_id, 'moderate', 'open');

DO $$
BEGIN
    BEGIN
        INSERT INTO oltp.location (openaq_location_id, name, city, country, latitude, longitude)
        VALUES (-9002, 'Bad Latitude', 'Budapest', 'HU', 100, 19.0402);
        RAISE EXCEPTION 'Expected invalid latitude to be rejected';
    EXCEPTION WHEN check_violation THEN
        NULL;
    END;

    BEGIN
        INSERT INTO oltp.measurement_raw (sensor_id, measured_at, value, unit)
        VALUES (-1, '2026-01-01T00:00:00Z', 1, 'ug/m3');
        RAISE EXCEPTION 'Expected invalid sensor FK to be rejected';
    EXCEPTION WHEN foreign_key_violation THEN
        NULL;
    END;

    BEGIN
        INSERT INTO oltp.threshold_rule (parameter_id, city, warning_level, min_value)
        VALUES ((SELECT parameter_id FROM oltp.parameter WHERE code = 'verify_pm25'), 'Budapest', 'impossible', 1);
        RAISE EXCEPTION 'Expected invalid warning level to be rejected';
    EXCEPTION WHEN check_violation THEN
        NULL;
    END;
END $$;

ROLLBACK;
