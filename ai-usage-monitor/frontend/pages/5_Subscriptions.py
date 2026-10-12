import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
import streamlit as st
from components.api_client import get_json, send
from components.ui import configure, filters

configure("Subscriptions")
filters()
st.title("Subscriptions")
st.caption("Consumer plans and API accounts are separate. Allowances typed here are manual, with the time they were recorded.")
try:
    payload = get_json("/api/subscriptions", {"include_demo": st.session_state.get("include_demo", True)})
except ConnectionError as exc:
    st.error(str(exc))
    st.stop()
if payload.get("includes_demo_data"):
    st.warning("Demo watermark — subscription rows marked Demo were seeded locally and were not read from a provider.")
rows = payload.get("subscriptions") or []
if rows:
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
else:
    st.info("No subscription records. Add one below if you want to track a plan fee you pay outside the API.")
for row in rows:
    if row.get("usage_page_url"):
        st.markdown(f"**{row['provider']} {row['plan']}** — [account page]({row['usage_page_url']})")
st.subheader("Add a manual record")
with st.form("subscription"):
    provider = st.selectbox("Provider", ["openai", "anthropic", "xai"])
    plan = st.text_input("Plan")
    fee = st.number_input("Monthly fee", min_value=0.0, step=1.0)
    currency = st.text_input("Currency", value="USD")
    billing_day = st.number_input("Billing day", min_value=1, max_value=28, value=1)
    allowance = st.text_area("Allowance you can see (optional)")
    observed = st.text_area("Usage you observed (optional)")
    notes = st.text_area("Notes")
    submitted = st.form_submit_button("Save subscription")
if submitted:
    if not plan:
        st.error("Plan name is required.")
    else:
        try:
            send(
                "POST",
                "/api/subscriptions",
                {
                    "provider": provider,
                    "plan": plan,
                    "monthly_fee": fee,
                    "currency": currency,
                    "billing_day": int(billing_day),
                    "manual_allowance": allowance or None,
                    "manually_recorded_usage": observed or None,
                    "notes": notes or None,
                },
            )
        except ConnectionError as exc:
            st.error(str(exc))
        else:
            st.success("Saved as a manual record.")
            st.rerun()
st.subheader("Delete a manual record")
live_ids = [str(row["id"]) for row in rows if not row["is_demo"]]
if not live_ids:
    st.caption("Demo subscriptions stay in place until demo data is removed from Settings.")
else:
    choice = st.selectbox("Record id", live_ids)
    if st.button("Delete selected subscription"):
        try:
            send("DELETE", f"/api/subscriptions/{choice}")
        except ConnectionError as exc:
            st.error(str(exc))
        else:
            st.rerun()
