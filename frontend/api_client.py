from __future__ import annotations

import os
from typing import Any

import pandas as pd
import requests
import streamlit as st


API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8001").rstrip("/")


def api_request(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json: dict[str, Any] | None = None,
    default: Any = None,
) -> Any:
    try:
        response = requests.request(
            method,
            f"{API_BASE_URL}{path}",
            params=params,
            json=json,
            timeout=10,
        )
        response.raise_for_status()
        if not response.content:
            return default
        return response.json()
    except requests.RequestException as exc:
        st.error(f"API request failed: {exc}")
        return default


def api_get(path: str, *, params: dict[str, Any] | None = None, default: Any = None) -> Any:
    return api_request("GET", path, params=params, default=default)


def api_post(path: str, *, json: dict[str, Any], default: Any = None) -> Any:
    return api_request("POST", path, json=json, default=default)


def api_patch(path: str, *, json: dict[str, Any], default: Any = None) -> Any:
    return api_request("PATCH", path, json=json, default=default)


def dataframe_from(rows: Any) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)
