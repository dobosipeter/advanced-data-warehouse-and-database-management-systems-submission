DELETE FROM dw.fact_air_quality_measurement
WHERE measurement_value < 0;
