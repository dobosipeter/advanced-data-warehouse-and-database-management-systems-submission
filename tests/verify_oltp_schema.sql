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

INSERT INTO oltp.threshold_rule (parameter_id, city, warning_level, min_value)
VALUES
    (:verify_parameter_id, 'Budapest', 'low', 0.0000),
    (:verify_parameter_id, 'Budapest', 'moderate', 10.0000),
    (:verify_parameter_id, 'Budapest', 'high', 25.0000),
    (:verify_parameter_id, 'Budapest', 'critical', 50.0000);

INSERT INTO oltp.sensor (openaq_sensor_id, location_id, parameter_id, unit)
VALUES (-9001, :verify_location_id, :verify_parameter_id, 'ug/m3')
RETURNING sensor_id \gset verify_

INSERT INTO oltp.measurement_raw (sensor_id, measured_at, value, unit, ingestion_run_id)
VALUES (:verify_sensor_id, '2026-01-01T00:00:00Z', 12.3400, 'ug/m3', :verify_ingestion_run_id)
RETURNING measurement_id \gset verify_

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM oltp.pollution_alert
        WHERE measurement_id = (
            SELECT measurement_id
            FROM oltp.measurement_raw
            WHERE sensor_id = (SELECT sensor_id FROM oltp.sensor WHERE openaq_sensor_id = -9001)
              AND measured_at = '2026-01-01T00:00:00Z'
        )
          AND alert_level = 'moderate'
          AND status = 'open'
    ) THEN
        RAISE EXCEPTION 'Expected trigger-generated pollution alert to exist';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM audit.pollution_alert_outbox
        WHERE measurement_id = (
            SELECT measurement_id
            FROM oltp.measurement_raw
            WHERE sensor_id = (SELECT sensor_id FROM oltp.sensor WHERE openaq_sensor_id = -9001)
              AND measured_at = '2026-01-01T00:00:00Z'
        )
          AND event_type = 'created'
          AND current_status = 'open'
    ) THEN
        RAISE EXCEPTION 'Expected alert outbox to contain created event';
    END IF;

    UPDATE oltp.pollution_alert
    SET status = 'reviewed',
        reviewed_at = now()
    WHERE measurement_id = (
        SELECT measurement_id
        FROM oltp.measurement_raw
        WHERE sensor_id = (SELECT sensor_id FROM oltp.sensor WHERE openaq_sensor_id = -9001)
          AND measured_at = '2026-01-01T00:00:00Z'
    );

    IF NOT EXISTS (
        SELECT 1
        FROM audit.pollution_alert_outbox
        WHERE measurement_id = (
            SELECT measurement_id
            FROM oltp.measurement_raw
            WHERE sensor_id = (SELECT sensor_id FROM oltp.sensor WHERE openaq_sensor_id = -9001)
              AND measured_at = '2026-01-01T00:00:00Z'
        )
          AND event_type = 'status_changed'
          AND previous_status = 'open'
          AND current_status = 'reviewed'
    ) THEN
        RAISE EXCEPTION 'Expected alert outbox to contain status change event';
    END IF;

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
