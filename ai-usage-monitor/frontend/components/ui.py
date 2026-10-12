"""Dashboard chrome shared by every page."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st
from components.api_client import get_json
from components.formatters import fmt_int, fmt_money, fmt_number, fmt_percent, fmt_time

TIMEZONES = ["Asia/Singapore", "UTC", "America/New_York", "Europe/London", "Asia/Kolkata"]


def configure(title: str) -> None:
    st.set_page_config(page_title=f"{title} · AI Usage Monitor", page_icon="◌", layout="wide")


def filters() -> dict:
    st.sidebar.title("AI Usage Monitor")
    theme = st.sidebar.radio("Theme", ["Dark", "Light"], horizontal=True, key="theme")
    _css(theme)
    preset = st.sidebar.radio("Range", ["Today", "7D", "30D", "Custom"], index=2, key="preset")
    timezone = st.sidebar.selectbox("Timezone", TIMEZONES, index=0, key="timezone")
    today = date.today()
    if preset == "Today":
        start = end = today
    elif preset == "7D":
        start, end = today - timedelta(days=6), today
    elif preset == "30D":
        start, end = today - timedelta(days=29), today
    else:
        picked = st.sidebar.date_input("Custom range", value=(today - timedelta(days=29), today), key="custom_range")
        if isinstance(picked, tuple) and len(picked) == 2:
            start, end = picked
        else:
            start = end = today
    provider = st.sidebar.selectbox("Provider", ["All", "openai", "anthropic", "xai"], key="provider")
    model = st.sidebar.text_input("Model", key="model")
    source = st.sidebar.selectbox(
        "Source",
        ["All", "provider_usage", "provider_cost", "agent_import", "litellm"],
        key="source",
    )
    project = st.sidebar.text_input("Project", key="project")
    agent = st.sidebar.text_input("Agent", key="agent")
    include_demo = st.sidebar.checkbox("Include demo data", value=True, key="include_demo")
    st.sidebar.caption("Demo rows stay labeled and are omitted from live totals when this is off.")
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "timezone": timezone,
        "provider": None if provider == "All" else provider,
        "model": model or None,
        "source": None if source == "All" else source,
        "project": project or None,
        "agent": agent or None,
        "include_demo": include_demo,
        "theme": theme.lower(),
    }


def guard(payload_loader):
    try:
        with st.spinner("Loading"):
            return payload_loader()
    except ConnectionError as exc:
        st.error(str(exc))
        st.info("Start the API with `uvicorn backend.main:app --host 127.0.0.1 --port 8000` from the project folder.")
        st.stop()
        return None


def banner(payload: dict) -> None:
    kind = payload.get("data_classification")
    if kind == "demo":
        st.warning(
            "Demo watermark — every figure on this page is synthetic. "
            "It is not provider-reported billing. Hide demo data before treating any number as live."
        )
    elif kind == "mixed":
        st.warning("This page mixes labeled demo rows with live rows. Hide demo data to see live totals only.")
    elif kind == "empty":
        st.info("No rows in this range. Connect a provider from Settings, or load the synthetic demo.")


def kpi_row(kpis: dict, tz_name: str) -> None:
    cards = [
        ("Billed API cost", fmt_money(kpis.get("billed_api_cost_usd")), "Provider-reported"),
        ("Estimated cost", fmt_money(kpis.get("gateway_estimated_cost_usd")), "Not added to billed"),
        ("Subscription fees", fmt_money(kpis.get("subscription_fees_usd")), "USD plans only"),
        ("Input tokens", fmt_int(kpis.get("input_tokens"), kpis.get("input_tokens_partial", False)), "As reported"),
        ("Output tokens", fmt_int(kpis.get("output_tokens")), "As reported"),
        ("Cache read", fmt_int(kpis.get("cache_read_tokens")), "Separate from input"),
        ("Cache write", fmt_int(kpis.get("cache_write_tokens")), "When the source reports it"),
        ("Requests", fmt_int(kpis.get("request_count"), kpis.get("request_count_partial", False)), "Blank stays N/A"),
        ("Avg latency", fmt_number(kpis.get("avg_latency_ms")) + (" ms" if kpis.get("avg_latency_ms") is not None else ""), "Instrumented logs only"),
        ("Error rate", fmt_percent(kpis.get("error_rate")), "Instrumented logs only"),
        ("Budget use", fmt_percent(kpis.get("budget_utilization")), "Calendar month, billed only"),
        ("Last sync", fmt_time(kpis.get("last_sync_at"), tz_name), "Provider fetch"),
    ]
    for offset in range(0, len(cards), 4):
        columns = st.columns(4)
        for column, (label, value, note) in zip(columns, cards[offset : offset + 4], strict=False):
            with column:
                st.markdown(
                    f"<div class='kpi'><div class='kpi-label'>{label}</div>"
                    f"<div class='kpi-value'>{value}</div><div class='kpi-note'>{note}</div></div>",
                    unsafe_allow_html=True,
                )


def line_chart(rows: list[dict], value: str, title: str, theme: str) -> None:
    present = [row for row in rows if row.get(value) is not None]
    if not present:
        st.info(f"No {title.lower()} in this range. Missing days are omitted rather than drawn as zero.")
        return
    frame = pd.DataFrame(present)
    fig = px.line(frame, x="date", y=value, markers=True, title=title)
    _layout(fig, theme)
    st.plotly_chart(fig, use_container_width=True)


def bar_chart(frame: pd.DataFrame, x: str, y: str, title: str, theme: str, color: str | None = None) -> None:
    if frame.empty:
        st.info("Nothing to chart in this range.")
        return
    fig = px.bar(frame, x=x, y=y, color=color, title=title, barmode="group")
    _layout(fig, theme)
    st.plotly_chart(fig, use_container_width=True)


def stacked_tokens(models: list[dict], theme: str) -> None:
    records = []
    for row in models:
        for label, key in (("Input", "input_tokens"), ("Output", "output_tokens")):
            if row.get(key) is None:
                continue
            records.append({"model": f"{row['provider']} · {row['model']}", "tokens": row[key], "kind": label})
    if not records:
        st.info("No token volumes in this range.")
        return
    fig = px.bar(pd.DataFrame(records), x="model", y="tokens", color="kind", title="Token volume", barmode="stack")
    _layout(fig, theme)
    st.plotly_chart(fig, use_container_width=True)


def status_badge(status: str) -> str:
    labels = {
        "not_configured": "Not Configured",
        "configured": "Configured",
        "connected": "Connected",
        "insufficient_permissions": "Insufficient permissions",
        "unsupported": "Unsupported",
        "rate_limited": "Rate limited",
        "failed": "Failed",
        "stale": "Stale",
        "unverified": "Not verified",
    }
    return labels.get(status, status)


def load_overview(params: dict) -> dict:
    return get_json("/api/overview", params)


def _layout(fig, theme: str) -> None:
    fig.update_layout(
        template="plotly_dark" if theme == "dark" else "plotly_white",
        height=380,
        margin={"l": 16, "r": 16, "t": 48, "b": 16},
        legend_title_text="",
    )


def _css(theme: str) -> None:
    if theme == "Light":
        colors = ("#f4f6fb", "#ffffff", "#1d2433", "#5c6b82", "#dde3ee")
    else:
        colors = ("#0e1117", "#171c25", "#f2f5f8", "#9aa8bd", "#2a3342")
    page, card, text, muted, border = colors
    st.markdown(
        f"""
        <style>
        .stApp {{ background: {page}; color: {text}; }}
        .kpi {{
            background: {card};
            border: 1px solid {border};
            border-radius: 12px;
            padding: 14px 16px;
            min-height: 112px;
            margin-bottom: 12px;
        }}
        .kpi-label {{ color: {muted}; font-size: 0.82rem; letter-spacing: 0.02em; }}
        .kpi-value {{ font-size: 1.45rem; font-weight: 650; margin: 6px 0; }}
        .kpi-note {{ color: {muted}; font-size: 0.78rem; }}
        </style>
        """,
        unsafe_allow_html=True,
    )
