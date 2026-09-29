"""Dashboard runtime 6 panel cho Day 13 — đọc data/logs.jsonl, khớp config/dashboard.yaml.

Chạy:
    .venv/Scripts/python -m streamlit run scripts/dashboard.py

Dashboard tự refresh theo ``dashboard.refresh_seconds``; time range mặc định 60 phút
đúng contract, có thể kéo dài hơn qua sidebar để nhìn lại incident cũ.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

CONFIG_PATH = REPO_ROOT / "config" / "dashboard.yaml"
LOG_PATH = REPO_ROOT / "data" / "logs.jsonl"


@st.cache_data(ttl=15)
def load_logs() -> pd.DataFrame:
    rows: list[dict] = []
    if LOG_PATH.exists():
        with LOG_PATH.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["ts"] = pd.to_datetime(df["ts"], utc=True, errors="coerce")
    return df.dropna(subset=["ts"]).sort_values("ts")


def load_contract() -> dict:
    with CONFIG_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f)["dashboard"]


def add_threshold(fig: go.Figure, aggregation: str, operator: str, value: float, unit: str) -> None:
    """Vẽ ngưỡng SLO/guardrail từ contract lên panel."""
    color = "#d62728" if operator == "lte" else "#2ca02c"
    fig.add_hline(
        y=value,
        line_dash="dash",
        line_color=color,
        annotation_text=f"{aggregation} {operator} {value}{unit and f' {unit}' or ''}",
        annotation_position="top left",
    )


def empty_figure(title: str) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(title=title, height=280, margin=dict(l=40, r=20, t=50, b=30))
    return fig


def main() -> None:
    st.set_page_config(page_title="Day 13 Monitoring Dashboard", layout="wide")
    contract = load_contract()
    df = load_logs()

    st.title(contract["title"])
    st.caption(
        f"Nguồn: `{contract['panels'][0]['source']}` — time range mặc định "
        f"{contract['time_range_minutes']} phút, refresh {contract['refresh_seconds']}s "
        "(dashed line = threshold/SLO từ contract)."
    )

    range_minutes = st.sidebar.number_input(
        "Time range (phút)",
        min_value=5,
        max_value=24 * 60,
        value=int(contract["time_range_minutes"]),
        help="Contract mặc định 60 phút; tăng lên để nhìn lại incident cũ.",
    )
    st.sidebar.metric("Log lines", len(df))
    now = pd.Timestamp.now(tz="UTC")
    cutoff = now - pd.Timedelta(minutes=range_minutes)
    window = df[df["ts"] >= cutoff] if not df.empty else df

    resp = window[window["event"] == "response_sent"] if not window.empty else window
    req = window[window["event"] == "request_received"] if not window.empty else window
    fail = window[window["event"] == "request_failed"] if not window.empty else window

    panels = {p["id"]: p for p in contract["panels"]}
    st.subheader(f"Time range: {cutoff.strftime('%H:%M')} – {now.strftime('%H:%M')} UTC")

    # ---- Panel 1: latency -------------------------------------------------
    p = panels["latency"]
    st.markdown(f"### {p['title']}")
    if resp.empty:
        fig = empty_figure(p["title"])
    else:
        lat_sorted = sorted(resp["latency_ms"].tolist())
        def pct(series: list[float], q: float) -> float:
            k = (len(series) - 1) * q / 100
            f0, c0 = int(k), min(int(k) + 1, len(series) - 1)
            return series[f0] + (series[c0] - series[f0]) * (k - f0)

        # P50/P95/P99 theo cửa sổ 5 phút để thấy dạng sóng
        resp2 = resp.set_index("ts")
        grouped = resp2["latency_ms"].rolling("5min").apply(
            lambda s: pct(sorted(s.tolist()), 95), raw=False
        )
        p50 = resp2["latency_ms"].rolling("5min").apply(
            lambda s: pct(sorted(s.tolist()), 50), raw=False
        )
        p99 = resp2["latency_ms"].rolling("5min").apply(
            lambda s: pct(sorted(s.tolist()), 99), raw=False
        )
        ttft_p95 = resp2["ttft_ms"].rolling("5min").apply(
            lambda s: pct(sorted(s.tolist()), 95), raw=False
        )
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=p50.index, y=p50.values, name="latency P50 (5m window)", line=dict(color="#1f77b4")))
        fig.add_trace(go.Scatter(x=grouped.index, y=grouped.values, name="latency P95 (5m window)", line=dict(color="#ff7f0e")))
        fig.add_trace(go.Scatter(x=p99.index, y=p99.values, name="latency P99 (5m window)", line=dict(color="#d62728")))
        fig.add_trace(go.Scatter(x=ttft_p95.index, y=ttft_p95.values, name="TTFT P95 (5m window)", line=dict(color="#2ca02c")))
        th = p["threshold"]
        add_threshold(fig, th["aggregation"], th["operator"], th["value"], p["unit"])
        overall = {
            "P50": round(pct(lat_sorted, 50)),
            "P95": round(pct(lat_sorted, 95)),
            "P99": round(pct(lat_sorted, 99)),
            "TTFT P95": round(pct(sorted(resp["ttft_ms"].tolist()), 95)),
        }
        st.caption("Overall: " + " | ".join(f"{k} = {v} ms" for k, v in overall.items()))
    fig.update_layout(height=300, margin=dict(l=40, r=20, t=30, b=30), yaxis_title=p["unit"])
    st.plotly_chart(fig, use_container_width=True)

    # ---- Panel 2: traffic -------------------------------------------------
    p = panels["traffic"]
    st.markdown(f"### {p['title']}")
    if req.empty:
        fig = empty_figure(p["title"])
    else:
        per_min = req.set_index("ts").resample("1min").size()
        fig = go.Figure(go.Bar(x=per_min.index, y=per_min.values, marker_color="#9467bd", name="requests/min"))
        fig.add_trace(go.Scatter(x=per_min.index, y=[per_min.mean()] * len(per_min), name="avg req/min", line=dict(dash="dot", color="#555")))
        th = p["threshold"]
        add_threshold(fig, th["aggregation"], th["operator"], th["value"], "")
    fig.update_layout(height=300, margin=dict(l=40, r=20, t=30, b=30), yaxis_title=p["unit"])
    st.plotly_chart(fig, use_container_width=True)

    # ---- Panel 3: errors + retrieval success ------------------------------
    p = panels["errors"]
    st.markdown(f"### {p['title']}")
    total_req = max(len(req), 1)
    error_rate = len(fail) / total_req * 100
    tool_vals = [v for v in resp.get("tool_success", []).tolist()] if not resp.empty else []
    tool_known = [v for v in tool_vals if v is not None]
    retrieval_rate = (sum(1 for v in tool_known if v) / len(tool_known) * 100) if tool_known else 100.0
    c1, c2, c3 = st.columns(3)
    c1.metric("Error rate (%)", f"{error_rate:.2f}", help="count(request_failed)/count(request_received)")
    c2.metric("Retrieval success (%)", f"{retrieval_rate:.2f}", help="tool_success==true / các request có tool_success")
    c3.metric("Total failed", len(fail))
    if not window.empty:
        by_ts = pd.DataFrame({
            "ts": pd.concat([req["ts"], fail["ts"]]).sort_values().tolist(),
        })
        err_by_min = fail.set_index("ts").resample("1min").size().reindex(
            req.set_index("ts").resample("1min").size().index, fill_value=0
        )
        rate = err_by_min / per_min.reindex(err_by_min.index).fillna(1) * 100
        fig = go.Figure(go.Bar(x=rate.index, y=rate.values, marker_color="#d62728", name="error rate %/min"))
        fig.add_trace(go.Scatter(x=rate.index, y=[retrieval_rate] * len(rate), name="retrieval success %", line=dict(color="#2ca02c")))
        th = p["threshold"]
        add_threshold(fig, th["aggregation"], th["operator"], th["value"], "%")
    else:
        fig = empty_figure(p["title"])
    fig.update_layout(height=300, margin=dict(l=40, r=20, t=30, b=30), yaxis_title=p["unit"])
    st.plotly_chart(fig, use_container_width=True)

    # ---- Panel 4: cost -----------------------------------------------------
    p = panels["cost"]
    st.markdown(f"### {p['title']}")
    if resp.empty:
        fig = empty_figure(p["title"])
    else:
        cost_by_min = resp.set_index("ts")["cost_usd"].resample("1min").sum()
        cumulative = cost_by_min.cumsum()
        fig = go.Figure()
        fig.add_trace(go.Bar(x=cost_by_min.index, y=cost_by_min.values, name="cost/min (USD)", marker_color="#8c564b"))
        fig.add_trace(go.Scatter(x=cumulative.index, y=cumulative.values, name="cumulative (USD)", line=dict(color="#e377c2")))
        st.caption(f"Total cost in range: ${resp['cost_usd'].sum():.4f}")
        th = p["threshold"]
        add_threshold(fig, th["aggregation"], th["operator"], th["value"], "USD")
    fig.update_layout(height=300, margin=dict(l=40, r=20, t=30, b=30), yaxis_title=p["unit"])
    st.plotly_chart(fig, use_container_width=True)

    # ---- Panel 5: tokens ---------------------------------------------------
    p = panels["tokens"]
    st.markdown(f"### {p['title']}")
    if resp.empty:
        fig = empty_figure(p["title"])
    else:
        tin = resp.set_index("ts")["tokens_in"].resample("1min").sum()
        tout = resp.set_index("ts")["tokens_out"].resample("1min").sum()
        fig = go.Figure()
        fig.add_trace(go.Bar(x=tin.index, y=tin.values, name="tokens_in", marker_color="#17becf"))
        fig.add_trace(go.Bar(x=tout.index, y=tout.values, name="tokens_out", marker_color="#bcbd22"))
        fig.update_layout(barmode="stack")
        st.caption(
            f"Total: tokens_in = {int(resp['tokens_in'].sum())} | tokens_out = {int(resp['tokens_out'].sum())}"
        )
        th = p["threshold"]
        add_threshold(fig, th["aggregation"], th["operator"], th["value"], "tokens")
    fig.update_layout(height=300, margin=dict(l=40, r=20, t=30, b=30), yaxis_title=p["unit"])
    st.plotly_chart(fig, use_container_width=True)

    # ---- Panel 6: quality --------------------------------------------------
    p = panels["quality"]
    st.markdown(f"### {p['title']}")
    if resp.empty:
        fig = empty_figure(p["title"])
    else:
        q = resp.set_index("ts")["quality_score"].resample("1min").mean()
        fig = go.Figure(go.Scatter(x=q.index, y=q.values, name="mean quality", line=dict(color="#2ca02c")))
        st.caption(f"Mean quality overall: {resp['quality_score'].mean():.3f}")
        th = p["threshold"]
        add_threshold(fig, th["aggregation"], th["operator"], th["value"], "")
    fig.update_layout(height=300, margin=dict(l=40, r=20, t=30, b=30), yaxis_title=p["unit"], yaxis_range=[0, 1.05])
    st.plotly_chart(fig, use_container_width=True)

    st.divider()
    st.caption(
        "Contract: `config/dashboard.yaml` (schema_version=1, 6 panel bắt buộc). "
        "Validator: `python scripts/validate_dashboard.py`. "
        "Langfuse là nơi mở trace/prompt để điều tra sâu — dashboard này dùng logs.jsonl làm nguồn chuẩn."
    )


if __name__ == "__main__":
    main()
