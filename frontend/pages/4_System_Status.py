import streamlit as st

from api_client import api_get, dataframe_from


st.set_page_config(page_title="System Status", layout="wide")
st.title("System Status")

health = api_get("/health", default={})
runs = dataframe_from(api_get("/ingestion-runs", default=[]))

left, right = st.columns(2)
left.metric("API", health.get("status", "unavailable"))
right.metric("Database", health.get("database", "unknown"))

st.subheader("Ingestion runs")
if runs.empty:
    st.info("No ingestion runs available.")
else:
    st.dataframe(
        runs[
            [
                "ingestion_run_id",
                "run_type",
                "status",
                "started_at",
                "finished_at",
                "records_inserted",
                "records_failed",
                "error_message",
            ]
        ],
        use_container_width=True,
        hide_index=True,
    )
