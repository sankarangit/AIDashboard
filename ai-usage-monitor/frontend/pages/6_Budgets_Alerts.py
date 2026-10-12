import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
import streamlit as st
from components.api_client import get_json, send
from components.formatters import fmt_money, fmt_percent
from components.ui import configure, filters

configure("Budgets and Alerts")
params = filters()
st.title("Budgets and alerts")
try:
    data = get_json("/api/budgets", params)
except ConnectionError as exc:
    st.error(str(exc))
    st.stop()
if any(row.get("is_demo") for row in data.get("budgets") or []):
    st.warning("Demo watermark — budget bars below include synthetic billed spend and synthetic budget amounts.")
st.caption(data.get("note"))
st.write(f"Calendar month {data.get('period')}: billed API spend {fmt_money(data.get('month_billed_usd'))}")
for budget in data.get("budgets") or []:
    label = budget["provider"] or "Combined API spend"
    ratio = budget["utilization"]
    st.markdown(f"**{label}** — {fmt_money(budget['spend_usd'])} of {fmt_money(budget['monthly_budget_usd'])} ({fmt_percent(ratio)})")
    if ratio is None:
        st.caption("Utilization is N/A because there is no provider-billed spend in this month.")
    else:
        st.progress(min(ratio, 1.0))
        percent = ratio * 100
        if percent >= 100:
            st.error("100% of this budget has been reached on provider-billed spend.")
        elif percent >= 80:
            st.warning("80% of this budget has been reached.")
        elif percent >= 50:
            st.info("50% of this budget has been reached.")
alerts = data.get("alerts") or []
st.subheader("Alert history")
if alerts:
    st.dataframe(pd.DataFrame(alerts), use_container_width=True, hide_index=True)
else:
    st.caption("No thresholds have been crossed.")
st.caption("Email is not sent for demo budgets. Live email also requires ALERT_EMAIL_ENABLED and SMTP settings in the environment.")
st.subheader("Add a live budget")
with st.form("budget"):
    provider = st.selectbox("Scope", ["combined", "openai", "anthropic", "xai"])
    amount = st.number_input("Monthly billed budget (USD)", min_value=0.01, value=100.0)
    threshold = st.number_input("Primary threshold %", min_value=1, max_value=100, value=80)
    submitted = st.form_submit_button("Save budget")
if submitted:
    try:
        send(
            "POST",
            "/api/budgets",
            {
                "provider": None if provider == "combined" else provider,
                "monthly_budget_usd": amount,
                "threshold_percent": int(threshold),
                "enabled": True,
            },
        )
    except ConnectionError as exc:
        st.error(str(exc))
    else:
        st.success("Budget saved.")
        st.rerun()
