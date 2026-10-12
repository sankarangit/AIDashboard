import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
import streamlit as st
from components.api_client import get_json
from components.ui import banner, configure, filters, guard, line_chart

configure("Usage Trends")
params = filters()
data = guard(lambda: get_json("/api/usage", params))
st.title("Usage trends")
banner(data)
st.caption("Dates are grouped in the selected timezone. A missing request count stays blank.")
daily = data.get("daily") or []
line_chart(
    [{"date": row["date"], "tokens": row["input_tokens"]} for row in daily if row.get("input_tokens") is not None],
    "tokens",
    "Daily input tokens",
    params["theme"],
)
line_chart(
    [{"date": row["date"], "tokens": row["output_tokens"]} for row in daily if row.get("output_tokens") is not None],
    "tokens",
    "Daily output tokens",
    params["theme"],
)
rows = data.get("rows") or []
frame = pd.DataFrame(rows)
st.subheader("Activity")
if frame.empty:
    st.info("No usage events in this range.")
else:
    st.dataframe(frame, use_container_width=True, hide_index=True)
    st.download_button(
        "Download CSV",
        data=frame.to_csv(index=False).encode("utf-8"),
        file_name="usage_trends.csv",
        mime="text/csv",
    )
st.caption(f"Timezone for this export's local_date column: {params['timezone']}. Stored timestamps remain UTC.")
