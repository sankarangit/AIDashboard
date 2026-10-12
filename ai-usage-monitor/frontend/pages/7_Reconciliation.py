import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
import streamlit as st
from components.api_client import get_json
from components.ui import banner, configure, filters

configure("Reconciliation")
params = filters()
st.title("Reconciliation")
try:
    data = get_json("/api/reconciliation", params)
except ConnectionError as exc:
    st.error(str(exc))
    st.stop()
banner(data)
st.info(data.get("note"))
frame = pd.DataFrame(data.get("providers") or [])
if frame.empty:
    st.info("No cost rows to reconcile.")
else:
    display = frame.copy()
    for column in (
        "billed_api_cost_usd",
        "gateway_estimated_cost_usd",
        "variance_usd",
        "variance_percent",
        "unmatched_estimated_cost_usd",
    ):
        display[column] = display[column].apply(lambda value: "N/A" if value is None or pd.isna(value) else value)
    st.dataframe(display, use_container_width=True, hide_index=True)
st.caption("Variance is the gateway estimate minus provider-billed cost. The two amounts are never added together.")
