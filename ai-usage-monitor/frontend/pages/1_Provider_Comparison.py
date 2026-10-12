import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
import streamlit as st
from components.ui import (
    banner,
    bar_chart,
    configure,
    filters,
    guard,
    load_overview,
    stacked_tokens,
)

configure("Provider Comparison")
params = filters()
data = guard(lambda: load_overview(params))
st.title("Provider comparison")
banner(data)
st.caption("OpenAI, Anthropic, and xAI are compared on billed API cost. Estimated gateway cost stays in its own column.")
frame = pd.DataFrame(data["by_provider"])
if frame.empty:
    st.info("No providers to compare.")
else:
    billed = frame.dropna(subset=["billed_api_cost_usd"])
    bar_chart(billed, "provider", "billed_api_cost_usd", "Billed API cost", params["theme"])
    estimated = frame.dropna(subset=["gateway_estimated_cost_usd"])
    bar_chart(estimated, "provider", "gateway_estimated_cost_usd", "Gateway-estimated cost (not billed)", params["theme"])
    stacked_tokens(data["top_models"], params["theme"])
    show = frame.copy()
    for column in ("billed_api_cost_usd", "gateway_estimated_cost_usd", "input_tokens", "output_tokens", "request_count"):
        show[column] = show[column].apply(lambda value: "N/A" if value is None or (isinstance(value, float) and pd.isna(value)) else value)
    st.dataframe(show, use_container_width=True, hide_index=True)
    st.subheader("Reporting coverage")
    coverage_rows = []
    for row in data["by_provider"]:
        coverage = row["coverage"]
        coverage_rows.append(
            {
                "Provider": row["provider"],
                "Billed cost": "Reported" if coverage["provider_billed"] else "No billed rows",
                "Usage tokens": "Reported" if coverage["provider_usage"] else "No usage rows",
                "Gateway estimate": "Present" if coverage["gateway_estimated"] else "No estimate rows",
            }
        )
    st.dataframe(pd.DataFrame(coverage_rows), use_container_width=True, hide_index=True)
