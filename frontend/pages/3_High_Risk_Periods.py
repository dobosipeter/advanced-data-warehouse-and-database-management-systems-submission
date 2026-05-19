import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard_support import (
    ALL_OPTION,
    combined_date_bounds,
    filter_frame,
    load_alerts,
    load_locations,
    load_measurements,
    normalize_date_selection,
    option_values,
)


WEEKDAY_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


st.set_page_config(page_title="High-Risk Periods", layout="wide")
st.title("High-Risk Periods")
st.caption("Identify when and where alerts concentrate — by weekday, hour, pollutant, and station.")

locations = load_locations()
measurements = load_measurements()
alerts = load_alerts()

if alerts.empty:
    st.info("No alerts available.")
    st.stop()

default_start, default_end = combined_date_bounds((alerts, "generated_at"), (measurements, "measured_at"))
city_options = [ALL_OPTION, *option_values(locations if not locations.empty else alerts, "city")]
selected_city = st.sidebar.selectbox("City", city_options, key="risk-city")

station_source = locations.rename(columns={"name": "location_name"}) if not locations.empty else alerts
station_source = filter_frame(station_source, city=selected_city, location=ALL_OPTION, parameter=ALL_OPTION)
station_options = [ALL_OPTION, *option_values(station_source, "location_name")]
selected_station = st.sidebar.selectbox("Station", station_options, key="risk-station")

parameter_source = filter_frame(alerts, city=selected_city, location=selected_station, parameter=ALL_OPTION)
parameter_options = [ALL_OPTION, *option_values(parameter_source, "parameter_code")]
selected_parameter = st.sidebar.selectbox("Pollutant", parameter_options, key="risk-parameter")

date_selection = st.sidebar.date_input(
    "Date range",
    value=(default_start, default_end),
    min_value=default_start,
    max_value=default_end,
    key="risk-dates",
)
date_range = normalize_date_selection(date_selection, default_start, default_end)

filtered_alerts = filter_frame(
    alerts,
    city=selected_city,
    location=selected_station,
    parameter=selected_parameter,
    date_range=date_range,
    time_column="generated_at",
)

if filtered_alerts.empty:
    st.info("No alerts match the selected filters.")
    st.stop()

heatmap_source = filtered_alerts.copy()
heatmap_source["weekday"] = heatmap_source["generated_at"].dt.day_name()
heatmap_source["hour"] = heatmap_source["generated_at"].dt.hour
heatmap = (
    heatmap_source.groupby(["weekday", "hour"]).size().reset_index(name="alert_count")
    .assign(weekday=lambda frame: pd.Categorical(frame["weekday"], categories=WEEKDAY_ORDER, ordered=True))
    .sort_values(["weekday", "hour"])
)
pivot = heatmap.pivot(index="weekday", columns="hour", values="alert_count").fillna(0)

metrics = st.columns(4)
metrics[0].metric("Total alerts", len(filtered_alerts))
metrics[1].metric("Critical alerts", int((filtered_alerts["alert_level"] == "critical").sum()))
metrics[2].metric("Stations affected", int(filtered_alerts["location_name"].nunique()))
metrics[3].metric("Pollutants affected", int(filtered_alerts["parameter_code"].nunique()))

st.divider()

left, right = st.columns([2, 1])

with left:
    st.subheader("Alert heatmap by weekday and hour")
    figure = px.imshow(
        pivot,
        labels={"x": "Hour", "y": "Weekday", "color": "Alerts"},
        aspect="auto",
        color_continuous_scale="OrRd",
    )
    figure.update_layout(height=420, margin=dict(l=10, r=10, t=20, b=10))
    st.plotly_chart(figure, use_container_width=True)

with right:
    st.subheader("Alert severity mix")
    severity_counts = filtered_alerts["alert_level"].value_counts().rename_axis("alert_level").reset_index(name="count")
    severity_chart = px.bar(severity_counts, x="alert_level", y="count", color="alert_level")
    severity_chart.update_layout(height=420, margin=dict(l=10, r=10, t=20, b=10), showlegend=False)
    st.plotly_chart(severity_chart, use_container_width=True)

st.divider()

lower_left, lower_right = st.columns(2)

with lower_left:
    st.subheader("Alerts by pollutant")
    pollutant_counts = (
        filtered_alerts.groupby("parameter_code").size().reset_index(name="count").sort_values("count", ascending=False)
    )
    pollutant_chart = px.bar(pollutant_counts, x="parameter_code", y="count", color="parameter_code")
    pollutant_chart.update_layout(height=360, margin=dict(l=10, r=10, t=20, b=10), showlegend=False)
    st.plotly_chart(pollutant_chart, use_container_width=True)

with lower_right:
    st.subheader("Alerts by station")
    station_counts = (
        filtered_alerts.groupby("location_name").size().reset_index(name="count").sort_values("count", ascending=False)
    )
    station_chart = px.bar(station_counts.head(10), x="location_name", y="count", color="location_name")
    station_chart.update_layout(height=360, margin=dict(l=10, r=10, t=20, b=10), showlegend=False)
    st.plotly_chart(station_chart, use_container_width=True)

st.divider()

st.subheader("Recent high-risk alerts")
st.dataframe(
    filtered_alerts.sort_values("generated_at", ascending=False)[
        [
            "generated_at",
            "city",
            "location_name",
            "parameter_code",
            "alert_level",
            "measurement_value",
            "status",
        ]
    ],
    use_container_width=True,
    hide_index=True,
)
