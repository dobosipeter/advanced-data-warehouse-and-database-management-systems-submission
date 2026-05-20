DO $$
DECLARE
    is_partitioned BOOLEAN;
    partition_count INTEGER;
    brin_index_count INTEGER;
    plan_text TEXT;
BEGIN
    SELECT c.relkind = 'p'
    INTO is_partitioned
    FROM pg_class AS c
    JOIN pg_namespace AS n
        ON n.oid = c.relnamespace
    WHERE n.nspname = 'oltp'
      AND c.relname = 'measurement_raw';

    IF is_partitioned IS DISTINCT FROM true THEN
        RAISE EXCEPTION 'Expected oltp.measurement_raw to be a partitioned table';
    END IF;

    SELECT count(*)
    INTO partition_count
    FROM pg_inherits
    WHERE inhparent = 'oltp.measurement_raw'::regclass;

    IF partition_count < 12 THEN
        RAISE EXCEPTION 'Expected monthly measurement partitions, found %', partition_count;
    END IF;

    SELECT count(*)
    INTO brin_index_count
    FROM pg_index AS i
    JOIN pg_class AS idx
        ON idx.oid = i.indexrelid
    JOIN pg_class AS tbl
        ON tbl.oid = i.indrelid
    JOIN pg_namespace AS n
        ON n.oid = tbl.relnamespace
    JOIN pg_am AS am
        ON am.oid = idx.relam
    WHERE n.nspname = 'oltp'
      AND tbl.relname LIKE 'measurement_raw%'
      AND am.amname = 'brin';

    IF brin_index_count = 0 THEN
        RAISE EXCEPTION 'Expected BRIN index on measurement partitions';
    END IF;
END $$;

BEGIN;
SET LOCAL enable_seqscan = off;

DO $$
DECLARE
    plan_line TEXT;
    plan_lines TEXT[] := ARRAY[]::TEXT[];
    plan_text TEXT;
BEGIN
    FOR plan_line IN
        EXECUTE 'EXPLAIN SELECT count(*) FROM oltp.measurement_raw WHERE measured_at >= TIMESTAMPTZ ''2026-01-01'' AND measured_at < TIMESTAMPTZ ''2026-02-01'''
    LOOP
        plan_lines := array_append(plan_lines, plan_line);
    END LOOP;

    plan_text := array_to_string(plan_lines, E'\n');

    IF plan_text !~ 'Index Scan|Index Only Scan|Bitmap Index Scan' THEN
        RAISE EXCEPTION 'Expected EXPLAIN to use an index when seqscan is disabled. Plan: %', plan_text;
    END IF;

    RAISE NOTICE 'Partitioned measurement query plan:%', E'\n' || plan_text;
END $$;

ROLLBACK;
