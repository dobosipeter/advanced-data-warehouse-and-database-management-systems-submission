import streamlit as st

from api_client import api_get, api_patch, dataframe_from


st.set_page_config(page_title="Alerts", layout="wide")
st.title("Alerts")

status_filter = st.sidebar.selectbox("Status", ["all", "open", "reviewed", "closed"])
level_filter = st.sidebar.selectbox("Level", ["all", "moderate", "high", "critical", "low"])
params = {}
if status_filter != "all":
    params["status"] = status_filter
if level_filter != "all":
    params["level"] = level_filter
alerts = dataframe_from(api_get("/alerts", params=params, default=[]))

if alerts.empty:
    st.info("No alerts available.")
    st.stop()

st.dataframe(
    alerts[
        [
            "pollution_alert_id",
            "generated_at",
            "city",
            "location_name",
            "parameter_code",
            "alert_level",
            "status",
            "measurement_value",
            "threshold_value",
        ]
    ],
    use_container_width=True,
    hide_index=True,
)

st.subheader("Review alert")
alert_id = st.selectbox(
    "Alert",
    alerts["pollution_alert_id"].tolist(),
    format_func=lambda value: f"#{value}",
)
new_status = st.selectbox("New status", ["reviewed", "closed", "open"])
notes = st.text_area("Notes", height=100)

if st.button("Update alert"):
    result = api_patch(
        f"/alerts/{alert_id}",
        json={"status": new_status, "notes": notes or None},
        default=None,
    )
    if result:
        st.success("Alert updated.")
        st.rerun()
