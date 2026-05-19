import pandas as pd
import plotly.express as px
import streamlit as st

from api_client import api_get, dataframe_from

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
if measurements.empty:
    st.info("No measurements available yet.")
else:
    measurements["measured_at"] = pd.to_datetime(measurements["measured_at"], utc=True, errors="coerce")
    measurements["day"] = measurements["measured_at"].dt.date
    daily_avg = (
        measurements.groupby(["day", "parameter_code"], as_index=False)["value"]
        .mean()
        .rename(columns={"value": "daily_mean"})
    )
    chart = px.line(
        daily_avg.sort_values("day"),
        x="day",
        y="daily_mean",
        color="parameter_code",
        markers=True,
        labels={"day": "Date", "daily_mean": "Daily mean", "parameter_code": "Pollutant"},
    )
    chart.update_layout(height=340, margin=dict(l=10, r=10, t=10, b=10), legend_title_text="")
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
