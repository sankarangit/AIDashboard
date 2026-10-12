import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd
import streamlit as st
from components.ui import (
    banner,
    bar_chart,
    configure,
    filters,
    guard,
    kpi_row,
    line_chart,
    load_overview,
    status_badge,
)

configure("Overview")
params = filters()
data = guard(lambda: load_overview(params))
st.title("Overview")
banner(data)
st.caption(data.get("accounting_note", ""))
kpi_row(data["kpis"], params["timezone"])
left, right = st.columns(2)
with left:
    line_chart(data["daily_billed"], "cost_usd", "Daily billed API cost", params["theme"])
with right:
    line_chart(data["daily_billed"], "cumulative_usd", "Cumulative billed API cost", params["theme"])
providers = pd.DataFrame(data["by_provider"])
if not providers.empty and providers["billed_api_cost_usd"].notna().any():
    bar_chart(providers.dropna(subset=["billed_api_cost_usd"]), "provider", "billed_api_cost_usd", "Billed cost by provider", params["theme"])
else:
    st.info("No provider-billed cost in this range.")
st.subheader("Source coverage")
st.write(", ".join(data["source_coverage"]) if data["source_coverage"] else "No sources in this range.")
try:
    from components.api_client import get_json

    listing = get_json("/api/providers")["providers"]
except ConnectionError as exc:
    st.error(str(exc))
    listing = []
if listing:
    st.subheader("Connections")
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Provider": row["label"],
                    "Status": status_badge(row["connection_status"]),
                    "Credential": row["credential"],
                    "Last sync": row["last_sync_at"] or "N/A",
                    "Detail": row["last_error"] or "",
                }
                for row in listing
            ]
        ),
        use_container_width=True,
        hide_index=True,
    )
st.caption(data.get("cache_note", ""))
