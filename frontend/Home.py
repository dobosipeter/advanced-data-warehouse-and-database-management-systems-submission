import pandas as pd
import numpy as np
import plotly.graph_objects as go
import streamlit as st

from api_client import api_get, dataframe_from
from dashboard_support import load_measurement_series


def build_daily_prediction(series: pd.DataFrame, horizon_days: int = 14) -> pd.DataFrame:
    daily = (
        series[["day", "daily_mean"]]
        .dropna()
        .drop_duplicates("day")
        .sort_values("day")
        .set_index("day")
    )
    if len(daily) < 4:
        return pd.DataFrame()

    daily = daily.asfreq("D")
    daily["daily_mean"] = daily["daily_mean"].interpolate(limit_direction="both")
    values = daily["daily_mean"].astype(float)
    train_len = len(values)
    steps = np.arange(train_len, dtype=float)
    days_of_year = values.index.dayofyear.to_numpy(dtype=float)
    design = np.column_stack(
        [
            np.ones(train_len),
            steps,
            np.sin(2 * np.pi * days_of_year / 365.25),
            np.cos(2 * np.pi * days_of_year / 365.25),
        ]
    )
    try:
        coefficients, *_ = np.linalg.lstsq(design, values.to_numpy(), rcond=None)
    except np.linalg.LinAlgError:
        return pd.DataFrame()

    prediction_index = pd.date_range(
        values.index.min(),
        values.index.max() + pd.Timedelta(days=horizon_days),
        freq="D",
        tz=values.index.tz,
    )
    prediction_steps = np.arange(len(prediction_index), dtype=float)
    prediction_days = prediction_index.dayofyear.to_numpy(dtype=float)
    prediction_design = np.column_stack(
        [
            np.ones(len(prediction_index)),
            prediction_steps,
            np.sin(2 * np.pi * prediction_days / 365.25),
            np.cos(2 * np.pi * prediction_days / 365.25),
        ]
    )
    prediction_values = np.maximum(prediction_design @ coefficients, 0)
    return pd.DataFrame({"day": prediction_index, "predicted_daily_mean": prediction_values})

st.set_page_config(
    page_title="Air Quality Intelligence",
    layout="wide",
)

st.title("🌍 Air Quality Intelligence")
st.markdown(
    "Real-time air quality monitoring, alerting, and PM2.5 prediction system "
    "powered by [OpenAQ](https://openaq.org) data."
)

# --- System health KPIs ---
health = api_get("/health", default={})
locations = dataframe_from(api_get("/locations", default=[]))
measurements = dataframe_from(api_get("/measurements", params={"limit": 500}, default=[]))
measurement_series = load_measurement_series(limit=50000)
alerts = dataframe_from(api_get("/alerts", default=[]))

metric_columns = st.columns(4)
metric_columns[0].metric("API status", health.get("status", "unavailable"))
metric_columns[1].metric("Monitored stations", len(locations))
metric_columns[2].metric("Recent measurements", len(measurements))
open_count = int((alerts["status"] == "open").sum()) if not alerts.empty and "status" in alerts else 0
metric_columns[3].metric("Open alerts", open_count)

st.divider()

# --- Daily average trend (aggregated to avoid spaghetti) ---
st.subheader("Daily average concentration by pollutant")
if measurement_series.empty:
    st.info("No measurements available yet.")
else:
    measurement_series["measured_hour"] = pd.to_datetime(
        measurement_series["measured_hour"],
        utc=True,
        errors="coerce",
    )
    measurement_series = measurement_series.dropna(subset=["measured_hour", "average_value"])
    measurement_series["day"] = measurement_series["measured_hour"].dt.floor("D")
    daily_avg = (
        measurement_series.groupby(["day", "parameter_code"], as_index=False)
        .agg(daily_mean=("average_value", "mean"), measurement_count=("measurement_count", "sum"))
        .sort_values("day")
    )

    chart = go.Figure()
    for parameter, group in daily_avg.groupby("parameter_code", sort=True):
        group = group.sort_values("day")
        chart.add_trace(
            go.Scatter(
                x=group["day"],
                y=group["daily_mean"],
                mode="lines+markers",
                name=f"{parameter} measured",
                line=dict(width=2),
            )
        )
        prediction = build_daily_prediction(group, horizon_days=14)
        if not prediction.empty:
            chart.add_trace(
                go.Scatter(
                    x=prediction["day"],
                    y=prediction["predicted_daily_mean"],
                    mode="lines",
                    name=f"{parameter} predicted",
                    line=dict(width=2, dash="dash"),
                )
            )

    chart.update_layout(
        height=360,
        margin=dict(l=10, r=10, t=10, b=10),
        legend_title_text="",
        xaxis_title="Date",
        yaxis_title="Daily mean concentration",
    )
    st.caption("Solid lines are measured daily means. Dashed lines are per-pollutant model estimates over the historical window and the next 14 days.")
    st.plotly_chart(chart, use_container_width=True)

st.divider()

# --- Active alerts summary + worst station ---
left, right = st.columns([2, 1])

with left:
    st.subheader("Active alerts")
    if alerts.empty:
        st.info("No alerts available.")
    else:
        open_alerts = alerts[alerts["status"] == "open"] if "status" in alerts else alerts
        if open_alerts.empty:
            st.success("No open alerts — all clear!")
        else:
            st.dataframe(
                open_alerts[
                    ["generated_at", "city", "location_name", "parameter_code", "alert_level", "measurement_value"]
                ].head(10),
                use_container_width=True,
                hide_index=True,
            )

with right:
    st.subheader("Worst station (latest)")
    if measurements.empty:
        st.info("No station ranking available.")
    else:
        worst = measurements.sort_values("value", ascending=False).iloc[0]
        st.metric(worst["location_name"], f"{worst['value']:.2f} {worst['unit']}", worst["parameter_code"])
        st.caption(f"{worst['city']} · {worst['measured_at']:%Y-%m-%d %H:%M} UTC")

st.divider()

# --- Page guide ---
st.subheader("📄 Pages")
st.markdown(
    """
| Page | Description |
|------|-------------|
| **Station Explorer** | Drill into a single station's time-series and sensor details. |
| **Threshold Management** | Create and edit alert threshold rules per city/pollutant. |
| **Alerts** | Browse, filter, and review triggered pollution alerts. |
| **System Status** | Check API health and recent ingestion run history. |
| **Air Quality Overview** | Filtered KPIs, trend charts, and station rankings. |
| **High-Risk Periods** | Heatmaps and breakdowns of when/where alerts concentrate. |
| **Prediction Insights** | Compare ML predictions against actuals with error metrics. |
| **Data Operations** | Monitor data completeness, gaps, and pipeline run status. |
"""
)
