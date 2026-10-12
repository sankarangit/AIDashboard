import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
import streamlit as st
from components.api_client import get_json
from components.ui import banner, bar_chart, configure, filters, guard

configure("Coding Agents")
params = filters()
data = guard(lambda: get_json("/api/agents", params))
st.title("Coding agents")
banner(data)
st.info(data.get("note") or "Agent rows do not describe Claude, ChatGPT, or Grok subscription caps.")
frame = pd.DataFrame(data.get("agents") or [])
if frame.empty:
    st.info("No agent telemetry in this range. Import a CSV or JSONL file from Settings, or load the demo.")
else:
    chart = frame.dropna(subset=["request_count"]) if "request_count" in frame else frame
    bar_chart(chart, "agent", "request_count", "API calls by agent", params["theme"])
    display = frame.copy()
    for column in ("input_tokens", "output_tokens", "request_count", "avg_latency_ms", "error_rate"):
        if column in display:
            display[column] = display[column].apply(lambda value: "N/A" if value is None or pd.isna(value) else value)
    st.dataframe(display, use_container_width=True, hide_index=True)
st.caption("Claude Code, Codex, and Grok Bot appear here only after an explicit import or a labeled demo row.")
