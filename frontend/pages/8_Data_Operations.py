import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard_support import (
    ALL_OPTION,
    combined_date_bounds,
    filter_frame,
    load_ingestion_runs,
    load_locations,
    load_measurements,
    normalize_date_selection,
    option_values,
)


GAP_THRESHOLD_HOURS = 6


st.set_page_config(page_title="Data Operations", layout="wide")
st.title("Data Operations")
st.caption("Monitor data completeness, ingestion pipeline health, and identify gaps in coverage.")

locations = load_locations()
measurements = load_measurements()
runs = load_ingestion_runs()

if measurements.empty and runs.empty:
    st.info("No operational data available.")
    st.stop()

default_start, default_end = combined_date_bounds((measurements, "measured_at"), (runs, "started_at"))
city_options = [ALL_OPTION, *option_values(locations if not locations.empty else measurements, "city")]
selected_city = st.sidebar.selectbox("City", city_options, key="ops-city")

station_source = locations.rename(columns={"name": "location_name"}) if not locations.empty else measurements
station_source = filter_frame(station_source, city=selected_city, location=ALL_OPTION, parameter=ALL_OPTION)
station_options = [ALL_OPTION, *option_values(station_source, "location_name")]
selected_station = st.sidebar.selectbox("Station", station_options, key="ops-station")

parameter_source = filter_frame(measurements, city=selected_city, location=selected_station, parameter=ALL_OPTION)
parameter_options = [ALL_OPTION, *option_values(parameter_source, "parameter_code")]
selected_parameter = st.sidebar.selectbox("Pollutant", parameter_options, key="ops-parameter")

date_selection = st.sidebar.date_input(
    "Date range",
    value=(default_start, default_end),
    min_value=default_start,
    max_value=default_end,
    key="ops-dates",
)
date_range = normalize_date_selection(date_selection, default_start, default_end)

filtered_measurements = filter_frame(
    measurements,
    city=selected_city,
    location=selected_station,
    parameter=selected_parameter,
    date_range=date_range,
    time_column="measured_at",
)
filtered_runs = filter_frame(
    runs,
    city=ALL_OPTION,
    location=ALL_OPTION,
    parameter=ALL_OPTION,
    date_range=date_range,
    time_column="started_at",
)

metrics = st.columns(4)
metrics[0].metric("Runs in range", len(filtered_runs))
metrics[1].metric("Failed or partial", int(filtered_runs["status"].isin(["failed", "partial"]).sum()) if not filtered_runs.empty else 0)
metrics[2].metric("Rows inserted", int(filtered_runs["records_inserted"].sum()) if not filtered_runs.empty else 0)
metrics[3].metric("Rows failed", int(filtered_runs["records_failed"].sum()) if not filtered_runs.empty else 0)

left, right = st.columns(2)

with left:
    st.subheader("Records per day")
    if filtered_measurements.empty:
        st.info("No measurements match the selected filters.")
    else:
        records_per_day = (
            filtered_measurements.assign(day=filtered_measurements["measured_at"].dt.date)
            .groupby("day")
            .size()
            .reset_index(name="records")
        )
        records_chart = px.bar(records_per_day, x="day", y="records")
        records_chart.update_layout(height=360, margin=dict(l=10, r=10, t=20, b=10))
        st.plotly_chart(records_chart, use_container_width=True)

with right:
    st.subheader("Run status")
    if filtered_runs.empty:
        st.info("No ingestion runs in the selected period.")
    else:
        status_counts = filtered_runs.groupby("status").size().reset_index(name="count")
        status_chart = px.bar(status_counts, x="status", y="count", color="status")
        status_chart.update_layout(height=360, margin=dict(l=10, r=10, t=20, b=10), showlegend=False)
        st.plotly_chart(status_chart, use_container_width=True)

st.subheader("Missing periods")
if filtered_measurements.empty:
    st.info("No measurements available to evaluate missing periods.")
else:
    gaps: list[dict[str, object]] = []
    grouping_columns = ["city", "location_name", "parameter_code"]
    for keys, group in filtered_measurements.sort_values("measured_at").groupby(grouping_columns):
        group = group.copy()
        group["previous_measured_at"] = group["measured_at"].shift()
        group["gap_duration"] = group["measured_at"] - group["previous_measured_at"]
        gap_rows = group[group["gap_duration"] > pd.Timedelta(hours=GAP_THRESHOLD_HOURS)]
        for _, row in gap_rows.iterrows():
            gaps.append(
                {
                    "city": keys[0],
                    "location_name": keys[1],
                    "parameter_code": keys[2],
                    "gap_start": row["previous_measured_at"],
                    "gap_end": row["measured_at"],
                    "gap_hours": round(row["gap_duration"].total_seconds() / 3600, 2),
                }
            )

    if not gaps:
        st.success(f"No gaps longer than {GAP_THRESHOLD_HOURS} hours were found.")
    else:
        st.dataframe(pd.DataFrame(gaps).sort_values("gap_hours", ascending=False), use_container_width=True, hide_index=True)

st.subheader("Recent ingestion runs")
if filtered_runs.empty:
    st.info("No ingestion runs available.")
else:
    st.dataframe(
        filtered_runs.sort_values("started_at", ascending=False)[
            [
                "started_at",
                "finished_at",
                "run_type",
                "status",
                "records_inserted",
                "records_failed",
                "error_message",
            ]
        ],
        use_container_width=True,
        hide_index=True,
    )
