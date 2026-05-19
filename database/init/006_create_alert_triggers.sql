CREATE TABLE IF NOT EXISTS audit.pollution_alert_outbox (
    alert_outbox_id BIGSERIAL PRIMARY KEY,
    pollution_alert_id BIGINT NOT NULL REFERENCES oltp.pollution_alert(pollution_alert_id) ON DELETE CASCADE,
    measurement_id BIGINT NOT NULL,
    measurement_measured_at TIMESTAMPTZ NOT NULL,
    threshold_rule_id BIGINT NOT NULL REFERENCES oltp.threshold_rule(threshold_rule_id),
    event_type TEXT NOT NULL CHECK (event_type IN ('created', 'status_changed')),
    previous_status TEXT CHECK (previous_status IS NULL OR previous_status IN ('open', 'reviewed', 'closed')),
    current_status TEXT NOT NULL CHECK (current_status IN ('open', 'reviewed', 'closed')),
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at TIMESTAMPTZ,
    FOREIGN KEY (measurement_id, measurement_measured_at)
        REFERENCES oltp.measurement_raw(measurement_id, measured_at) ON DELETE CASCADE,
    CONSTRAINT pollution_alert_outbox_status_change
        CHECK (event_type = 'created' OR previous_status IS DISTINCT FROM current_status)
);

CREATE INDEX IF NOT EXISTS idx_audit_pollution_alert_outbox_unprocessed
    ON audit.pollution_alert_outbox (processed_at, created_at)
    WHERE processed_at IS NULL;

CREATE OR REPLACE FUNCTION oltp.generate_pollution_alert_for_measurement()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    matched_rule_id BIGINT;
    matched_warning_level TEXT;
BEGIN
    SELECT tr.threshold_rule_id, tr.warning_level
    INTO matched_rule_id, matched_warning_level
    FROM oltp.sensor AS s
    JOIN oltp.location AS l
        ON l.location_id = s.location_id
    JOIN oltp.threshold_rule AS tr
        ON tr.parameter_id = s.parameter_id
       AND tr.city = l.city
       AND tr.is_active
    WHERE s.sensor_id = NEW.sensor_id
      AND tr.warning_level <> 'low'
      AND NEW.value >= tr.min_value
    ORDER BY tr.min_value DESC, tr.threshold_rule_id DESC
    LIMIT 1;

    IF matched_rule_id IS NOT NULL THEN
        INSERT INTO oltp.pollution_alert (measurement_id, measurement_measured_at, threshold_rule_id, alert_level, status)
        VALUES (NEW.measurement_id, NEW.measured_at, matched_rule_id, matched_warning_level, 'open')
        ON CONFLICT (measurement_id, threshold_rule_id) DO NOTHING;
    END IF;

    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION audit.enqueue_pollution_alert_event()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'UPDATE' AND NEW.status IS NOT DISTINCT FROM OLD.status THEN
        RETURN NEW;
    END IF;

    INSERT INTO audit.pollution_alert_outbox (
        pollution_alert_id,
        measurement_id,
        measurement_measured_at,
        threshold_rule_id,
        event_type,
        previous_status,
        current_status,
        payload
    )
    VALUES (
        NEW.pollution_alert_id,
        NEW.measurement_id,
        NEW.measurement_measured_at,
        NEW.threshold_rule_id,
        CASE
            WHEN TG_OP = 'INSERT' THEN 'created'
            ELSE 'status_changed'
        END,
        CASE
            WHEN TG_OP = 'INSERT' THEN NULL
            ELSE OLD.status
        END,
        NEW.status,
        jsonb_build_object(
            'alert_level', NEW.alert_level,
            'generated_at', NEW.generated_at,
            'reviewed_at', NEW.reviewed_at,
            'notes', NEW.notes
        )
    );

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_measurement_generate_pollution_alert ON oltp.measurement_raw;
CREATE TRIGGER trg_measurement_generate_pollution_alert
AFTER INSERT ON oltp.measurement_raw
FOR EACH ROW
EXECUTE FUNCTION oltp.generate_pollution_alert_for_measurement();

DROP TRIGGER IF EXISTS trg_pollution_alert_enqueue_event ON oltp.pollution_alert;
CREATE TRIGGER trg_pollution_alert_enqueue_event
AFTER INSERT OR UPDATE OF status ON oltp.pollution_alert
FOR EACH ROW
EXECUTE FUNCTION audit.enqueue_pollution_alert_event();
