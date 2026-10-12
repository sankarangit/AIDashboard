import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
import streamlit as st
from components.api_client import get_json, request, send
from components.ui import configure, filters, status_badge

configure("Settings")
filters()
st.title("Settings and connections")
st.caption("Credentials stay in the local environment. This page shows only whether a key is present.")
try:
    listing = get_json("/api/providers")["providers"]
    settings = get_json("/api/settings")
except ConnectionError as exc:
    st.error(str(exc))
    st.stop()
for row in listing:
    with st.container(border=True):
        st.markdown(f"### {row['label']}")
        st.write(f"Status: **{status_badge(row['connection_status'])}**")
        st.write(f"Credential: `{row['credential']}` (`{row['env_var']}`)")
        st.write(row["last_error"] or "No stored error.")
        caps = row["capabilities"]
        st.caption(
            "Reports tokens: {tokens}. Costs: {costs}. Requests: {requests}. Latency: {latency}.".format(**caps)
        )
        if caps.get("coverage"):
            st.caption(caps["coverage"])
        left, middle, right = st.columns(3)
        with left:
            if st.button("Test connection", key=f"test-{row['name']}"):
                try:
                    result = send("POST", f"/api/providers/{row['name']}/test-connection")
                except ConnectionError as exc:
                    st.error(str(exc))
                else:
                    st.write(f"{status_badge(result['status'])}: {result['message']}")
        with middle:
            if st.button("Sync now", key=f"sync-{row['name']}"):
                try:
                    result = send("POST", f"/api/providers/{row['name']}/sync")
                except ConnectionError as exc:
                    st.error(str(exc))
                else:
                    st.write(f"{status_badge(result['status'])}: {result['message']} Inserted {result['inserted']}.")
        with right:
            enabled = st.toggle("Enabled", value=row["enabled"], key=f"enabled-{row['name']}")
            if enabled != row["enabled"]:
                try:
                    send("PUT", f"/api/providers/{row['name']}", {"enabled": enabled})
                except ConnectionError as exc:
                    st.error(str(exc))
                else:
                    st.rerun()
st.subheader("Demo data")
st.write("The dashboard loads without API keys. Demo rows are synthetic and labeled.")
if st.button("Load synthetic demo"):
    try:
        send("POST", "/api/demo/seed")
    except ConnectionError as exc:
        st.error(str(exc))
    else:
        st.success("Demo data is available. Turn on Include demo data in the sidebar.")
        st.rerun()
if st.button("Delete demo data"):
    try:
        send("DELETE", "/api/demo")
    except ConnectionError as exc:
        st.error(str(exc))
    else:
        st.success("Demo rows were removed. Live rows were left in place.")
        st.rerun()
st.subheader("Preferences")
with st.form("prefs"):
    zone_options = ["Asia/Singapore", "UTC", "America/New_York", "Europe/London", "Asia/Kolkata"]
    timezone = st.selectbox(
        "Saved timezone",
        zone_options,
        index=zone_options.index(settings["timezone"]) if settings["timezone"] in zone_options else 0,
    )
    retention = st.number_input("Retention days (live rows, 0 keeps everything)", min_value=0, max_value=3650, value=int(settings["retention_days"]))
    include_demo = st.checkbox("Include demo data by default", value=bool(settings["include_demo"]))
    fx = st.text_input("FX JSON (optional)", value=settings.get("fx_usd_rates") or "")
    saved = st.form_submit_button("Save preferences")
if saved:
    try:
        send(
            "PUT",
            "/api/settings",
            {
                "timezone": timezone,
                "retention_days": int(retention),
                "include_demo": include_demo,
                "fx_usd_rates": fx,
            },
        )
    except ConnectionError as exc:
        st.error(str(exc))
    else:
        st.success("Preferences saved.")
st.subheader("Import an agent log")
st.caption("Choose a CSV or JSONL file yourself. The app does not scan your home directory. Prompt and response columns are discarded.")
upload = st.file_uploader("Agent export", type=["csv", "jsonl"])
if upload is not None and st.button("Import file"):
    try:
        result = request(
            "POST",
            "/api/imports",
            files={"upload": (upload.name, upload.getvalue(), "text/plain")},
        )
    except ConnectionError as exc:
        st.error(str(exc))
    else:
        st.write(result)
        if result.get("rejected_reasons"):
            st.dataframe(pd.DataFrame({"reason": result["rejected_reasons"]}), hide_index=True)
st.caption("Email alerts stay off unless ALERT_EMAIL_ENABLED is true and SMTP variables are set in .env.")
