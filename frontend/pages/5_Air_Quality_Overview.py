import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard_support import (
    ALL_OPTION,
    combined_date_bounds,
    filter_frame,
    format_number,
    load_alerts,
    load_locations,
    load_measurements,
    normalize_date_selection,
    option_values,
)


st.set_page_config(page_title="Air Quality Overview", layout="wide")
st.title("Air Quality Overview")
st.caption("Filtered KPIs, trend charts, and station rankings across all monitored locations.")

locations = load_locations()
measurements = load_measurements()
alerts = load_alerts()

if measurements.empty:
    st.info("No measurements available.")
    st.stop()

default_start, default_end = combined_date_bounds((measurements, "measured_at"))
city_options = [ALL_OPTION, *option_values(locations if not locations.empty else measurements, "city")]
selected_city = st.sidebar.selectbox("City", city_options, key="overview-city")

station_source = locations.rename(columns={"name": "location_name"}) if not locations.empty else measurements
station_source = filter_frame(station_source, city=selected_city, location=ALL_OPTION, parameter=ALL_OPTION)
station_options = [ALL_OPTION, *option_values(station_source, "location_name")]
selected_station = st.sidebar.selectbox("Station", station_options, key="overview-station")

parameter_source = filter_frame(
    measurements,
    city=selected_city,
    location=selected_station,
    parameter=ALL_OPTION,
)
parameter_options = [ALL_OPTION, *option_values(parameter_source, "parameter_code")]
selected_parameter = st.sidebar.selectbox("Pollutant", parameter_options, key="overview-parameter")

date_selection = st.sidebar.date_input(
    "Date range",
    value=(default_start, default_end),
    min_value=default_start,
    max_value=default_end,
    key="overview-dates",
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
filtered_alerts = filter_frame(
    alerts,
    city=selected_city,
    location=selected_station,
    parameter=selected_parameter,
    date_range=date_range,
    time_column="generated_at",
)

if filtered_measurements.empty:
    st.info("No measurements match the selected filters.")
    st.stop()

latest_measurement = filtered_measurements.sort_values("measured_at").iloc[-1]
week_cutoff = filtered_measurements["measured_at"].max() - pd.Timedelta(days=7)
this_week = filtered_measurements[filtered_measurements["measured_at"] >= week_cutoff]
latest_by_station = (
    filtered_measurements.sort_values("measured_at")
    .groupby(["city", "location_name", "parameter_code"], as_index=False)
    .tail(1)
    .sort_values("value", ascending=False)
)
worst_station = latest_by_station.iloc[0]

metrics = st.columns(4)
metrics[0].metric(
    "Latest value",
    f"{format_number(latest_measurement['value'], 2)} {latest_measurement['unit']}",
    latest_measurement["parameter_code"],
)
metrics[1].metric("Average this week", f"{format_number(this_week['value'].mean(), 2)} {latest_measurement['unit']}")
metrics[2].metric("Stations in filter", int(filtered_measurements["location_name"].nunique()))
metrics[3].metric("Open alerts", int((filtered_alerts["status"] == "open").sum()) if "status" in filtered_alerts else 0)

st.divider()

left, right = st.columns([2, 1])

with left:
    st.subheader("Trend chart")
    chart_data = filtered_measurements.copy()
    chart_data["day"] = chart_data["measured_at"].dt.date
    color_column = "parameter_code" if selected_parameter == ALL_OPTION else "location_name"

    # Aggregate to daily means to avoid spaghetti when many stations overlap
    num_series = chart_data[color_column].nunique()
    if num_series > 5:
        agg_data = (
            chart_data.groupby(["day", color_column], as_index=False)["value"]
            .mean()
            .rename(columns={"value": "daily_mean"})
            .sort_values("day")
        )
        chart = px.line(
            agg_data,
            x="day",
            y="daily_mean",
            color=color_column,
            markers=True,
            labels={"day": "Date", "daily_mean": "Daily mean"},
        )
        st.caption("Showing daily averages (many series detected).")
    else:
        chart = px.line(
            chart_data.sort_values("measured_at"),
            x="measured_at",
            y="value",
            color=color_column,
            markers=True,
            labels={"measured_at": "Measured at", "value": "Value"},
        )
    chart.update_layout(height=380, margin=dict(l=10, r=10, t=20, b=10), legend_title_text="")
    st.plotly_chart(chart, use_container_width=True)

with right:
    st.subheader("Worst station")
    st.metric(
        worst_station["location_name"],
        f"{format_number(worst_station['value'], 2)} {worst_station['unit']}",
        worst_station["parameter_code"],
    )
    st.caption(f"{worst_station['city']} · measured {worst_station['measured_at']:%Y-%m-%d %H:%M UTC}")

st.divider()

st.subheader("Latest values by station")
st.dataframe(
    latest_by_station[["measured_at", "city", "location_name", "parameter_code", "value", "unit"]],
    use_container_width=True,
    hide_index=True,
)
