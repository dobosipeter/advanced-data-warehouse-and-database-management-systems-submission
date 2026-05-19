import pandas as pd
import plotly.express as px
import streamlit as st

from api_client import api_get, dataframe_from

st.set_page_config(
    page_title="Air Quality Intelligence",
    layout="wide",
)

st.title("Air Quality Intelligence")

health = api_get("/health", default={})
locations = dataframe_from(api_get("/locations", default=[]))
measurements = dataframe_from(api_get("/measurements", params={"limit": 200}, default=[]))
alerts = dataframe_from(api_get("/alerts", default=[]))

metric_columns = st.columns(4)
metric_columns[0].metric("API", health.get("status", "unavailable"))
metric_columns[1].metric("Stations", len(locations))
metric_columns[2].metric("Measurements", len(measurements))
metric_columns[3].metric("Open alerts", int((alerts.get("status") == "open").sum()) if not alerts.empty else 0)

left, right = st.columns([2, 1])

with left:
    st.subheader("Latest measurements")
    if measurements.empty:
        st.info("No measurements available.")
    else:
        measurements["measured_at"] = pd.to_datetime(measurements["measured_at"])
        chart = px.line(
            measurements.sort_values("measured_at"),
            x="measured_at",
            y="value",
            color="parameter_code",
            markers=True,
            labels={"measured_at": "Measured at", "value": "Value", "parameter_code": "Parameter"},
        )
        chart.update_layout(height=360, margin=dict(l=10, r=10, t=20, b=10), legend_title_text="")
        st.plotly_chart(chart, use_container_width=True)
        st.dataframe(
            measurements[
                ["measured_at", "city", "location_name", "parameter_code", "value", "unit"]
            ],
            use_container_width=True,
            hide_index=True,
        )

with right:
    st.subheader("Active alerts")
    if alerts.empty:
        st.info("No alerts available.")
    else:
        open_alerts = alerts[alerts["status"] == "open"] if "status" in alerts else alerts
        st.dataframe(
            open_alerts[
                ["generated_at", "city", "location_name", "parameter_code", "alert_level", "measurement_value"]
            ],
            use_container_width=True,
            hide_index=True,
        )

    st.subheader("Worst station")
    if measurements.empty:
        st.info("No station ranking available.")
    else:
        worst = measurements.sort_values("value", ascending=False).iloc[0]
        st.metric(worst["location_name"], f"{worst['value']:.2f} {worst['unit']}", worst["parameter_code"])
