ALTER TABLE dw.fact_prediction
    ADD COLUMN IF NOT EXISTS risk_class_key SMALLINT REFERENCES dw.dim_risk_class(risk_class_key);
