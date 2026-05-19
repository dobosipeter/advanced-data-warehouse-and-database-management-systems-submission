# Indexing and Partitioning

This project treats `oltp.measurement_raw` as the primary operational time-series table. Measurements are written continuously by sensor and queried mostly by time window, city, station, parameter, ingestion run, and alert workflows.

## Measurement Partitioning

`oltp.measurement_raw` is partitioned by monthly ranges on `measured_at`.

Rationale:
- Time-window queries can prune unrelated months.
- Operational retention and archival can be handled one partition at a time.
- Large sequential ingestion batches remain append-friendly.
- Monthly partitions are coarse enough to avoid excessive partition count while still matching the expected dashboard and reporting windows.

The partitioned table uses a composite primary key `(measurement_id, measured_at)` because PostgreSQL requires unique constraints on partitioned tables to include the partition key. Tables that reference measurements store both `measurement_id` and `measurement_measured_at` for referential integrity.

## Index Choices

`idx_oltp_measurement_measured_at_brin`

BRIN index on `measured_at`. This is the PostgreSQL equivalent used here for compact time-series access. BRIN indexes are small and effective when measurements are mostly inserted in time order.

`idx_oltp_measurement_time_sensor`

B-tree index on `(measured_at DESC, sensor_id)`. This supports recent-measurement API queries and provides an index path for selective time-window lookups.

`UNIQUE (sensor_id, measured_at)`

Preserves ingestion idempotency. The OpenAQ worker uses this key to skip duplicate measurements.

`idx_oltp_measurement_sensor`

B-tree index for station/sensor joins from API and alert queries.

`idx_oltp_measurement_run`

B-tree index for tracing rows back to ingestion runs.

Other OLTP foreign-key columns also have B-tree indexes, and JSON raw API payloads use a GIN index for diagnostics.

## Verification

Run:

```bash
docker compose exec -T db psql -v ON_ERROR_STOP=1 -U air_quality -d air_quality -f /dev/stdin < tests/verify_partitioning_and_indexes.sql
```

The verification confirms:
- `oltp.measurement_raw` is a partitioned table.
- Monthly partitions exist.
- BRIN indexes exist on measurement partitions.
- `EXPLAIN` can use an index for a bounded `measured_at` query.
