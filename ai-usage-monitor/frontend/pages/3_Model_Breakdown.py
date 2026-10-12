import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
import streamlit as st
from components.api_client import get_json
from components.ui import banner, configure, filters, guard, stacked_tokens

configure("Model Breakdown")
params = filters()
data = guard(lambda: get_json("/api/usage", params))
st.title("Model breakdown")
banner(data)
st.caption("Cost per million tokens is billed cost divided by reported tokens. It is left as N/A when the provider did not report a model-level amount.")
stacked_tokens(data.get("by_model") or [], params["theme"])
rows = []
for row in data.get("by_model") or []:
    rows.append(
        {
            "Provider": row["provider"],
            "Model": row["model"],
            "Badge": row.get("badge"),
            "Input": "N/A" if row.get("input_tokens") is None else row["input_tokens"],
            "Output": "N/A" if row.get("output_tokens") is None else row["output_tokens"],
            "Cache read": "N/A" if row.get("cache_read_tokens") is None else row["cache_read_tokens"],
            "Cache write": "N/A" if row.get("cache_write_tokens") is None else row["cache_write_tokens"],
            "Requests": "N/A" if row.get("request_count") is None else row["request_count"],
            "Billed USD": "N/A" if row.get("billed_api_cost_usd") is None else row["billed_api_cost_usd"],
            "USD per 1M tokens": "N/A" if row.get("cost_per_million_tokens_usd") is None else row["cost_per_million_tokens_usd"],
            "Note": row.get("cost_note"),
        }
    )
if rows:
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
else:
    st.info("No model rows in this range.")
