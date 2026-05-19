import plotly.graph_objects as go
import streamlit as st

from dashboard_support import (
    ALL_OPTION,
    combined_date_bounds,
    filter_frame,
    format_number,
    load_locations,
    load_measurements,
    load_predictions,
    normalize_date_selection,
    option_values,
)


st.set_page_config(page_title="Prediction Insights", layout="wide")
st.title("Prediction Insights")
st.caption("Compare ML-predicted PM concentrations against observed actuals with error analysis.")

locations = load_locations()
measurements = load_measurements()
predictions = load_predictions()

if predictions.empty:
    st.info("No predictions available.")
    st.stop()

default_start, default_end = combined_date_bounds((predictions, "target_measured_at"), (measurements, "measured_at"))
city_options = [ALL_OPTION, *option_values(locations if not locations.empty else predictions, "city")]
selected_city = st.sidebar.selectbox("City", city_options, key="prediction-city")

station_source = locations.rename(columns={"name": "location_name"}) if not locations.empty else predictions
station_source = filter_frame(station_source, city=selected_city, location=ALL_OPTION, parameter=ALL_OPTION)
station_options = [ALL_OPTION, *option_values(station_source, "location_name")]
selected_station = st.sidebar.selectbox("Station", station_options, key="prediction-station")

parameter_source = filter_frame(predictions, city=selected_city, location=selected_station, parameter=ALL_OPTION)
parameter_options = [ALL_OPTION, *option_values(parameter_source, "parameter_code")]
selected_parameter = st.sidebar.selectbox("Pollutant", parameter_options, key="prediction-parameter")

date_selection = st.sidebar.date_input(
    "Date range",
    value=(default_start, default_end),
    min_value=default_start,
    max_value=default_end,
    key="prediction-dates",
)
date_range = normalize_date_selection(date_selection, default_start, default_end)

filtered_predictions = filter_frame(
    predictions,
    city=selected_city,
    location=selected_station,
    parameter=selected_parameter,
    date_range=date_range,
    time_column="target_measured_at",
)
filtered_measurements = filter_frame(
    measurements,
    city=selected_city,
    location=selected_station,
    parameter=selected_parameter,
    date_range=date_range,
    time_column="measured_at",
)

if filtered_predictions.empty:
    st.info("No predictions match the selected filters.")
    st.stop()

latest_prediction = filtered_predictions.sort_values("target_measured_at").iloc[-1]
available_errors = filtered_predictions["absolute_error"].dropna() if "absolute_error" in filtered_predictions else []

metrics = st.columns(4)
metrics[0].metric("Latest prediction", format_number(latest_prediction["predicted_value"], 2))
metrics[1].metric("Predicted risk", latest_prediction.get("risk_class_label") or "n/a")
metrics[2].metric("Model", latest_prediction["model_name"])
metrics[3].metric(
    "Mean absolute error",
    format_number(available_errors.mean() if len(available_errors) else None, 2),
)

figure = go.Figure()
if not filtered_measurements.empty:
    actual_series = filtered_measurements.sort_values("measured_at")
    # Aggregate to daily mean when many stations are shown to avoid spaghetti
    if actual_series["location_name"].nunique() > 3:
        actual_series = (
            actual_series.assign(day=actual_series["measured_at"].dt.date)
            .groupby("day", as_index=False)["value"]
            .mean()
        )
        figure.add_trace(
            go.Scatter(
                x=actual_series["day"],
                y=actual_series["value"],
                mode="lines+markers",
                name="Actual (daily avg)",
            )
        )
    else:
        figure.add_trace(
            go.Scatter(
                x=actual_series["measured_at"],
                y=actual_series["value"],
                mode="lines+markers",
                name="Actual",
            )
        )

prediction_series = filtered_predictions.sort_values("target_measured_at")
figure.add_trace(
    go.Scatter(
        x=prediction_series["target_measured_at"],
        y=prediction_series["predicted_value"],
        mode="lines+markers",
        line=dict(dash="dash"),
        name="Predicted",
    )
)

if "actual_value" in prediction_series and prediction_series["actual_value"].notna().any():
    matched = prediction_series[prediction_series["actual_value"].notna()]
    figure.add_trace(
        go.Scatter(
            x=matched["target_measured_at"],
            y=matched["actual_value"],
            mode="markers",
            marker=dict(size=10, symbol="diamond"),
            name="Actual at prediction time",
        )
    )

figure.update_layout(
    height=420,
    margin=dict(l=10, r=10, t=20, b=10),
    legend_title_text="",
    xaxis_title="Time",
    yaxis_title="PM concentration",
)
st.subheader("Actual vs predicted")
st.plotly_chart(figure, use_container_width=True)

st.subheader("Prediction details")
detail_columns = [
    "target_measured_at",
    "city",
    "location_name",
    "parameter_code",
    "predicted_value",
    "risk_class_label",
    "actual_value",
    "absolute_error",
    "model_name",
    "model_version",
]
st.dataframe(
    filtered_predictions.sort_values("target_measured_at", ascending=False)[detail_columns],
    use_container_width=True,
    hide_index=True,
)
