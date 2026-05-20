from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from api_client import api_get, dataframe_from


ALL_OPTION = "All"


@st.cache_data(ttl=120, show_spinner=False)
def load_locations() -> pd.DataFrame:
    return dataframe_from(api_get("/locations", default=[]))


@st.cache_data(ttl=120, show_spinner=False)
def load_measurements(limit: int = 1000) -> pd.DataFrame:
    frame = dataframe_from(api_get("/measurements", params={"limit": limit}, default=[]))
    return prepare_datetime_columns(frame, "measured_at")


@st.cache_data(ttl=120, show_spinner=False)
def load_measurement_series(limit: int = 50000) -> pd.DataFrame:
    frame = dataframe_from(api_get("/measurement-series", params={"limit": limit}, default=[]))
    return prepare_datetime_columns(frame, "measured_hour")


@st.cache_data(ttl=120, show_spinner=False)
def load_alerts(limit: int = 1000) -> pd.DataFrame:
    frame = dataframe_from(api_get("/alerts", params={"limit": limit}, default=[]))
    return prepare_datetime_columns(frame, "generated_at", "measured_at", "reviewed_at")


@st.cache_data(ttl=120, show_spinner=False)
def load_predictions(limit: int = 1000) -> pd.DataFrame:
    frame = dataframe_from(api_get("/predictions", params={"limit": limit}, default=[]))
    return prepare_datetime_columns(frame, "target_measured_at", "created_at")


@st.cache_data(ttl=120, show_spinner=False)
def load_ingestion_runs(limit: int = 200) -> pd.DataFrame:
    frame = dataframe_from(api_get("/ingestion-runs", params={"limit": limit}, default=[]))
    return prepare_datetime_columns(frame, "started_at", "finished_at")


def prepare_datetime_columns(frame: pd.DataFrame, *columns: str) -> pd.DataFrame:
    if frame.empty:
        return frame

    converted = frame.copy()
    for column in columns:
        if column in converted.columns:
            converted[column] = pd.to_datetime(converted[column], utc=True, errors="coerce")
    return converted


def option_values(frame: pd.DataFrame, column: str) -> list[str]:
    if frame.empty or column not in frame.columns:
        return []
    values = frame[column].dropna().astype(str).unique().tolist()
    return sorted(values)


def combined_date_bounds(*datasets: tuple[pd.DataFrame, str]) -> tuple[date, date]:
    dates: list[date] = []
    for frame, column in datasets:
        if frame.empty or column not in frame.columns:
            continue
        timestamps = pd.to_datetime(frame[column], utc=True, errors="coerce").dropna()
        if timestamps.empty:
            continue
        dates.append(timestamps.min().date())
        dates.append(timestamps.max().date())

    if not dates:
        today = pd.Timestamp.utcnow().date()
        return today, today

    return min(dates), max(dates)


def normalize_date_selection(selection: object, default_start: date, default_end: date) -> tuple[date, date]:
    if isinstance(selection, tuple) and len(selection) == 2:
        return selection
    if isinstance(selection, list) and len(selection) == 2:
        return selection[0], selection[1]
    if isinstance(selection, date):
        return selection, selection
    return default_start, default_end


def filter_frame(
    frame: pd.DataFrame,
    *,
    city: str = ALL_OPTION,
    location: str = ALL_OPTION,
    parameter: str = ALL_OPTION,
    date_range: tuple[date, date] | None = None,
    city_column: str = "city",
    location_column: str = "location_name",
    parameter_column: str = "parameter_code",
    time_column: str | None = None,
) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()

    filtered = frame.copy()

    if city != ALL_OPTION and city_column in filtered.columns:
        filtered = filtered[filtered[city_column] == city]
    if location != ALL_OPTION and location_column in filtered.columns:
        filtered = filtered[filtered[location_column] == location]
    if parameter != ALL_OPTION and parameter_column in filtered.columns:
        filtered = filtered[filtered[parameter_column] == parameter]

    if date_range and time_column and time_column in filtered.columns:
        start_date, end_date = date_range
        timestamps = pd.to_datetime(filtered[time_column], utc=True, errors="coerce")
        mask = timestamps.notna()
        mask &= timestamps >= pd.Timestamp(start_date).tz_localize("UTC")
        mask &= timestamps < (pd.Timestamp(end_date) + pd.Timedelta(days=1)).tz_localize("UTC")
        filtered = filtered[mask]

    return filtered


def format_number(value: float | int | None, digits: int = 1) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{float(value):,.{digits}f}"
