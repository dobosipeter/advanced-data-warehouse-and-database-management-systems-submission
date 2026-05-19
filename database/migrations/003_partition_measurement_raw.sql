BEGIN;

LOCK TABLE oltp.measurement_raw IN ACCESS EXCLUSIVE MODE;

DO $$
DECLARE
    is_partitioned BOOLEAN;
    partition_start DATE := DATE '2025-01-01';
    partition_end DATE := DATE '2027-02-01';
    current_month DATE;
    next_month DATE;
    partition_name TEXT;
    constraint_record RECORD;
BEGIN
    SELECT c.relkind = 'p'
    INTO is_partitioned
    FROM pg_class AS c
    JOIN pg_namespace AS n
        ON n.oid = c.relnamespace
    WHERE n.nspname = 'oltp'
      AND c.relname = 'measurement_raw';

    IF is_partitioned THEN
        RETURN;
    END IF;

    CREATE TABLE oltp.measurement_raw_partitioned (
        measurement_id BIGINT NOT NULL DEFAULT nextval('oltp.measurement_raw_measurement_id_seq'::regclass),
        sensor_id BIGINT NOT NULL REFERENCES oltp.sensor(sensor_id),
        measured_at TIMESTAMPTZ NOT NULL,
        value NUMERIC(12, 4) NOT NULL,
        unit TEXT NOT NULL,
        ingestion_run_id BIGINT REFERENCES oltp.ingestion_run_log(ingestion_run_id),
        raw_payload JSONB,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        PRIMARY KEY (measurement_id, measured_at),
        UNIQUE (sensor_id, measured_at),
        CONSTRAINT measurement_unit_not_blank CHECK (btrim(unit) <> ''),
        CONSTRAINT measurement_value_reasonable CHECK (value > -1000 AND value < 100000)
    ) PARTITION BY RANGE (measured_at);

    CREATE TABLE oltp.measurement_raw_default
        PARTITION OF oltp.measurement_raw_partitioned DEFAULT;

    current_month := partition_start;
    WHILE current_month < partition_end LOOP
        next_month := current_month + INTERVAL '1 month';
        partition_name := format('measurement_raw_%s', to_char(current_month, 'YYYY_MM'));

        EXECUTE format(
            'CREATE TABLE oltp.%I PARTITION OF oltp.measurement_raw_partitioned FOR VALUES FROM (%L) TO (%L)',
            partition_name,
            current_month::timestamptz,
            next_month::timestamptz
        );

        current_month := next_month;
    END LOOP;

    INSERT INTO oltp.measurement_raw_partitioned (
        measurement_id,
        sensor_id,
        measured_at,
        value,
        unit,
        ingestion_run_id,
        raw_payload,
        created_at
    )
    SELECT
        measurement_id,
        sensor_id,
        measured_at,
        value,
        unit,
        ingestion_run_id,
        raw_payload,
        created_at
    FROM oltp.measurement_raw;

    PERFORM setval(
        'oltp.measurement_raw_measurement_id_seq'::regclass,
        COALESCE((SELECT max(measurement_id) FROM oltp.measurement_raw_partitioned), 1),
        true
    );

    ALTER TABLE oltp.pollution_alert
        ADD COLUMN IF NOT EXISTS measurement_measured_at TIMESTAMPTZ;

    UPDATE oltp.pollution_alert AS pa
    SET measurement_measured_at = mr.measured_at
    FROM oltp.measurement_raw AS mr
    WHERE pa.measurement_id = mr.measurement_id
      AND pa.measurement_measured_at IS NULL;

    ALTER TABLE audit.pollution_alert_outbox
        ADD COLUMN IF NOT EXISTS measurement_measured_at TIMESTAMPTZ;

    UPDATE audit.pollution_alert_outbox AS outbox
    SET measurement_measured_at = mr.measured_at
    FROM oltp.measurement_raw AS mr
    WHERE outbox.measurement_id = mr.measurement_id
      AND outbox.measurement_measured_at IS NULL;

    FOR constraint_record IN
        SELECT conrelid::regclass AS table_name, conname
        FROM pg_constraint
        WHERE confrelid = 'oltp.measurement_raw'::regclass
    LOOP
        EXECUTE format('ALTER TABLE %s DROP CONSTRAINT %I', constraint_record.table_name, constraint_record.conname);
    END LOOP;

    DROP TRIGGER IF EXISTS trg_measurement_generate_pollution_alert ON oltp.measurement_raw;

    ALTER SEQUENCE oltp.measurement_raw_measurement_id_seq OWNED BY NONE;

    ALTER TABLE oltp.measurement_raw
        RENAME TO measurement_raw_unpartitioned_backup;

    ALTER TABLE oltp.measurement_raw_partitioned
        RENAME TO measurement_raw;

    ALTER SEQUENCE oltp.measurement_raw_measurement_id_seq OWNED BY oltp.measurement_raw.measurement_id;

    ALTER TABLE oltp.pollution_alert
        ALTER COLUMN measurement_measured_at SET NOT NULL,
        ADD CONSTRAINT pollution_alert_measurement_fk
            FOREIGN KEY (measurement_id, measurement_measured_at)
            REFERENCES oltp.measurement_raw(measurement_id, measured_at);

    ALTER TABLE audit.pollution_alert_outbox
        ALTER COLUMN measurement_measured_at SET NOT NULL,
        ADD CONSTRAINT pollution_alert_outbox_measurement_fk
            FOREIGN KEY (measurement_id, measurement_measured_at)
            REFERENCES oltp.measurement_raw(measurement_id, measured_at) ON DELETE CASCADE;

    CREATE OR REPLACE FUNCTION oltp.generate_pollution_alert_for_measurement()
    RETURNS TRIGGER
    LANGUAGE plpgsql
    AS $function$
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
            INSERT INTO oltp.pollution_alert (
                measurement_id,
                measurement_measured_at,
                threshold_rule_id,
                alert_level,
                status
            )
            VALUES (NEW.measurement_id, NEW.measured_at, matched_rule_id, matched_warning_level, 'open')
            ON CONFLICT (measurement_id, threshold_rule_id) DO NOTHING;
        END IF;

        RETURN NEW;
    END;
    $function$;

    CREATE OR REPLACE FUNCTION audit.enqueue_pollution_alert_event()
    RETURNS TRIGGER
    LANGUAGE plpgsql
    AS $function$
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
    $function$;

    CREATE TRIGGER trg_measurement_generate_pollution_alert
    AFTER INSERT ON oltp.measurement_raw
    FOR EACH ROW
    EXECUTE FUNCTION oltp.generate_pollution_alert_for_measurement();

    DROP TABLE oltp.measurement_raw_unpartitioned_backup;
END $$;

CREATE INDEX IF NOT EXISTS idx_oltp_measurement_measured_at_brin
    ON oltp.measurement_raw USING BRIN (measured_at);

CREATE INDEX IF NOT EXISTS idx_oltp_measurement_run
    ON oltp.measurement_raw (ingestion_run_id);

CREATE INDEX IF NOT EXISTS idx_oltp_measurement_sensor
    ON oltp.measurement_raw (sensor_id);

CREATE INDEX IF NOT EXISTS idx_oltp_measurement_time_sensor
    ON oltp.measurement_raw (measured_at DESC, sensor_id);

COMMIT;
