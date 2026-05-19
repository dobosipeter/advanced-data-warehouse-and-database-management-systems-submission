INSERT INTO oltp.parameter (openaq_parameter_id, code, display_name, description, preferred_unit)
VALUES
    (2, 'pm25', 'PM2.5', 'Fine particulate matter with diameter smaller than 2.5 micrometers', 'ug/m3'),
    (1, 'pm10', 'PM10', 'Particulate matter with diameter smaller than 10 micrometers', 'ug/m3'),
    (7, 'no2', 'NO2', 'Nitrogen dioxide', 'ug/m3'),
    (3, 'o3', 'O3', 'Ozone', 'ug/m3')
ON CONFLICT (code) DO UPDATE
SET
    openaq_parameter_id = EXCLUDED.openaq_parameter_id,
    display_name = EXCLUDED.display_name,
    description = EXCLUDED.description,
    preferred_unit = EXCLUDED.preferred_unit,
    is_active = true,
    updated_at = now();

INSERT INTO dw.dim_parameter (source_parameter_id, code, display_name, unit, is_active)
SELECT parameter_id, code, display_name, preferred_unit, is_active
FROM oltp.parameter
ON CONFLICT (code) DO UPDATE
SET
    source_parameter_id = EXCLUDED.source_parameter_id,
    display_name = EXCLUDED.display_name,
    unit = EXCLUDED.unit,
    is_active = EXCLUDED.is_active;

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

INSERT INTO oltp.threshold_rule (parameter_id, city, warning_level, min_value)
SELECT parameter_id, 'Budapest', warning_level, min_value
FROM oltp.parameter
CROSS JOIN (
    VALUES
        ('low', 0::numeric),
        ('moderate', 10::numeric),
        ('high', 25::numeric),
        ('critical', 50::numeric)
) AS rules (warning_level, min_value)
WHERE code = 'pm25'
ON CONFLICT (parameter_id, city, warning_level) DO UPDATE
SET
    min_value = EXCLUDED.min_value,
    is_active = true,
    updated_at = now();
