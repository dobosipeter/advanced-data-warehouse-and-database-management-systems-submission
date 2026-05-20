import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard_support import (
    ALL_OPTION,
    combined_date_bounds,
    filter_frame,
    format_number,
    load_alerts,
    load_locations,
    load_measurement_series,
    load_measurements,
    normalize_date_selection,
    option_values,
)


def build_hourly_forecast(series: pd.DataFrame, horizon_hours: int = 72) -> pd.DataFrame:
    hourly = (
        series[["measured_hour", "hourly_mean"]]
        .dropna()
        .drop_duplicates("measured_hour")
        .sort_values("measured_hour")
        .set_index("measured_hour")
    )
    if len(hourly) < 6:
        return pd.DataFrame()

    hourly = hourly.asfreq("h")
    hourly["hourly_mean"] = hourly["hourly_mean"].interpolate(limit_direction="both")
    values = hourly["hourly_mean"].astype(float)
    train_len = len(values)
    steps = np.arange(train_len, dtype=float)
    hours = values.index.hour.to_numpy(dtype=float)
    design = np.column_stack(
        [
            np.ones(train_len),
            steps,
            np.sin(2 * np.pi * hours / 24),
            np.cos(2 * np.pi * hours / 24),
        ]
    )
    try:
        coefficients, *_ = np.linalg.lstsq(design, values.to_numpy(), rcond=None)
    except np.linalg.LinAlgError:
        return pd.DataFrame()

    forecast_index = pd.date_range(
        values.index.max() + pd.Timedelta(hours=1),
        periods=horizon_hours,
        freq="h",
        tz=values.index.tz,
    )
    future_steps = np.arange(train_len, train_len + horizon_hours, dtype=float)
    future_hours = forecast_index.hour.to_numpy(dtype=float)
    future_design = np.column_stack(
        [
            np.ones(horizon_hours),
            future_steps,
            np.sin(2 * np.pi * future_hours / 24),
            np.cos(2 * np.pi * future_hours / 24),
        ]
    )
    forecast_values = np.maximum(future_design @ coefficients, 0)
    return pd.DataFrame({"measured_hour": forecast_index, "forecast_value": forecast_values})


st.set_page_config(page_title="Air Quality Overview", layout="wide")
st.title("Air Quality Overview")
st.caption("Measured hourly trends with per-city/pollutant forecasts for missing and upcoming data.")

locations = load_locations()
measurements = load_measurements(limit=10000)
measurement_series = load_measurement_series()
alerts = load_alerts()

if measurements.empty or measurement_series.empty:
    st.info("No measurements available.")
    st.stop()

default_start, default_end = combined_date_bounds((measurement_series, "measured_hour"))
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
forecast_horizon_hours = st.sidebar.slider("Forecast horizon", 24, 96, 72, 12)

filtered_measurements = filter_frame(
    measurements,
    city=selected_city,
    location=selected_station,
    parameter=selected_parameter,
    date_range=date_range,
    time_column="measured_at",
)
filtered_series = filter_frame(
    measurement_series,
    city=selected_city,
    location=ALL_OPTION,
    parameter=selected_parameter,
    date_range=date_range,
    parameter_column="parameter_code",
    time_column="measured_hour",
)
filtered_alerts = filter_frame(
    alerts,
    city=selected_city,
    location=selected_station,
    parameter=selected_parameter,
    date_range=date_range,
    time_column="generated_at",
)

if filtered_measurements.empty or filtered_series.empty:
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
    st.subheader("Measured history and forecast")
    agg_data = (
        filtered_series.groupby(["measured_hour", "city", "parameter_code"], as_index=False)
        .agg(hourly_mean=("average_value", "mean"), measurement_count=("measurement_count", "sum"))
        .sort_values("measured_hour")
    )
    chart = go.Figure()
    for (city, parameter), group in agg_data.groupby(["city", "parameter_code"], sort=True):
        group = group.sort_values("measured_hour")
        label = f"{city} · {parameter}"
        chart.add_trace(
            go.Scatter(
                x=group["measured_hour"],
                y=group["hourly_mean"],
                mode="lines",
                name=label,
                line=dict(width=2),
            )
        )
        forecast = build_hourly_forecast(group, horizon_hours=forecast_horizon_hours)
        if not forecast.empty:
            chart.add_trace(
                go.Scatter(
                    x=forecast["measured_hour"],
                    y=forecast["forecast_value"],
                    mode="lines",
                    name=f"{label} forecast",
                    line=dict(width=2, dash="dash"),
                )
            )

    chart.update_layout(
        height=430,
        margin=dict(l=10, r=10, t=20, b=10),
        legend_title_text="",
        xaxis_title="Time",
        yaxis_title="Hourly mean concentration",
    )
    st.caption("Solid lines are measured hourly means. Dashed lines are per-city/per-pollutant model forecasts.")
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
