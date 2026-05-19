import pandas as pd
import plotly.express as px
import streamlit as st

from api_client import api_get, dataframe_from


st.set_page_config(page_title="Station Explorer", layout="wide")
st.title("Station Explorer")

locations = dataframe_from(api_get("/locations", default=[]))

if locations.empty:
    st.info("No stations available.")
    st.stop()

city_options = sorted(locations["city"].dropna().unique())
selected_city = st.sidebar.selectbox("City", city_options)

city_locations = locations[locations["city"] == selected_city].sort_values("name")
station_name = st.sidebar.selectbox("Station", city_locations["name"].tolist())
station = city_locations[city_locations["name"] == station_name].iloc[0]

measurements = dataframe_from(
    api_get(
        "/measurements",
        params={"city": selected_city, "limit": 1000},
        default=[],
    )
)

st.subheader(station_name)
metrics = st.columns(4)
metrics[0].metric("City", station["city"])
metrics[1].metric("Country", station["country"])
metrics[2].metric("Active sensors", int(station["active_sensor_count"]))
metrics[3].metric("Latest", station["latest_measurement_at"] or "none")

if measurements.empty:
    st.info("No measurements available for this city.")
    st.stop()

station_measurements = measurements[measurements["location_name"] == station_name].copy()
if station_measurements.empty:
    st.info("No measurements available for this station.")
    st.stop()

station_measurements["measured_at"] = pd.to_datetime(station_measurements["measured_at"])
parameter_options = sorted(station_measurements["parameter_code"].dropna().unique())
selected_parameter = st.sidebar.selectbox("Parameter", parameter_options)
filtered = station_measurements[station_measurements["parameter_code"] == selected_parameter]

chart = px.line(
    filtered.sort_values("measured_at"),
    x="measured_at",
    y="value",
    markers=True,
    labels={"measured_at": "Measured at", "value": f"Value ({filtered['unit'].iloc[0]})"},
)
chart.update_layout(height=420, margin=dict(l=10, r=10, t=20, b=10))
st.plotly_chart(chart, use_container_width=True)

st.dataframe(
    filtered[["measured_at", "parameter_code", "value", "unit", "sensor_id", "ingestion_run_id"]],
    use_container_width=True,
    hide_index=True,
)
