import streamlit as st

from api_client import api_get, api_patch, api_post, dataframe_from


st.set_page_config(page_title="Threshold Management", layout="wide")
st.title("Threshold Management")

thresholds = dataframe_from(api_get("/thresholds", default=[]))
locations = dataframe_from(api_get("/locations", default=[]))
measurements = dataframe_from(api_get("/measurements", params={"limit": 1}, default=[]))

left, right = st.columns([2, 1])

with left:
    st.subheader("Threshold rules")
    if thresholds.empty:
        st.info("No threshold rules available.")
    else:
        st.dataframe(
            thresholds[
                [
                    "threshold_rule_id",
                    "city",
                    "parameter_code",
                    "warning_level",
                    "min_value",
                    "is_active",
                    "updated_at",
                ]
            ],
            use_container_width=True,
            hide_index=True,
        )

with right:
    st.subheader("Rule editor")
    city_options = sorted(locations["city"].dropna().unique()) if not locations.empty else ["Budapest"]
    parameter_options = (
        sorted(measurements["parameter_code"].dropna().unique()) if not measurements.empty else ["pm25"]
    )
    existing_labels = ["New rule"]
    existing_by_label = {}
    if not thresholds.empty:
        for row in thresholds.to_dict("records"):
            label = f"#{row['threshold_rule_id']} {row['city']} {row['parameter_code']} {row['warning_level']}"
            existing_labels.append(label)
            existing_by_label[label] = row

    selected_rule_label = st.selectbox("Rule", existing_labels)
    selected_rule = existing_by_label.get(selected_rule_label)
    default_city = selected_rule["city"] if selected_rule else city_options[0]
    default_parameter = selected_rule["parameter_code"] if selected_rule else parameter_options[0]
    default_level = selected_rule["warning_level"] if selected_rule else "high"
    if default_city not in city_options:
        city_options.append(default_city)
    if default_parameter not in parameter_options:
        parameter_options.append(default_parameter)

    with st.form("threshold_form"):
        city = st.selectbox("City", city_options, index=city_options.index(default_city))
        parameter_code = st.selectbox(
            "Parameter",
            parameter_options,
            index=parameter_options.index(default_parameter) if default_parameter in parameter_options else 0,
        )
        levels = ["low", "moderate", "high", "critical"]
        warning_level = st.selectbox("Warning level", levels, index=levels.index(default_level))
        min_value = st.number_input(
            "Minimum value",
            min_value=0.0,
            value=float(selected_rule["min_value"]) if selected_rule else 25.0,
            step=1.0,
        )
        is_active = st.checkbox("Active", value=bool(selected_rule["is_active"]) if selected_rule else True)
        submitted = st.form_submit_button("Save rule")

    if submitted:
        payload = {
            "parameter_code": parameter_code,
            "city": city,
            "warning_level": warning_level,
            "min_value": min_value,
            "is_active": is_active,
        }
        if selected_rule:
            result = api_patch(f"/thresholds/{selected_rule['threshold_rule_id']}", json=payload, default=None)
        else:
            result = api_post("/thresholds", json=payload, default=None)
        if result:
            st.success("Threshold saved.")
            st.rerun()
