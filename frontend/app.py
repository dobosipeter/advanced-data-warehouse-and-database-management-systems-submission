import streamlit as st

st.set_page_config(
    page_title="Air Quality Intelligence",
    layout="wide",
)

st.title("Air Quality Intelligence")
st.caption("Operational monitoring and data warehouse dashboard scaffold.")

left, right = st.columns(2)

with left:
    st.subheader("Operational Layer")
    st.write("Monitored stations, latest measurements, threshold rules, and alerts will appear here.")

with right:
    st.subheader("Warehouse Layer")
    st.write("Historical trends, risk classifications, and prediction results will appear here.")
