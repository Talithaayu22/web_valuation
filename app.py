from dataclasses import asdict, replace
from datetime import datetime, timezone, timedelta
from html import escape
import importlib
import json
import math
import re
import sys
from typing import Any, Tuple
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

# Explicitly reload valuation submodules to prevent stale sys.modules caching in Streamlit
for _mod_name in ("valuation.model", "valuation.data", "valuation.report_pdf", "valuation.export", "valuation.storage", "valuation.ui_table"):
    if _mod_name in sys.modules:
        try:
            importlib.reload(sys.modules[_mod_name])
        except Exception:
            pass

from valuation.ui_table import render_apple_table, parse_mapping_provenance

try:
    from valuation.data import clean_company_name, format_wib_retrieval
except ImportError:
    def clean_company_name(name: str) -> str:
        if not name:
            return ""
        cleaned = re.sub(r"^\s*perusahaan\s+perseroan\s*\(persero\)\s*", "", str(name), flags=re.IGNORECASE)
        cleaned = re.sub(r"\bperusahaan\s+perseroan\b", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\(persero\)", "", cleaned, flags=re.IGNORECASE)
        return re.sub(r"\s+", " ", cleaned).strip()

    def format_wib_retrieval(ts: Any) -> Tuple[str, str]:
        return "Offline Benchmark", "Offline Benchmark"

try:
    from valuation.data import (
        CATALOG, BILLION, demo_company, demo_peers, fetch_company, peer_record, ticker_symbol,
        get_default_peers_for_ticker, get_or_fetch_peers, rank_peers_similarity, get_company_idx_metadata
    )
except ImportError:
    from valuation.data import (
        CATALOG, BILLION, demo_company, fetch_company, peer_record, ticker_symbol,
        get_default_peers_for_ticker, rank_peers_similarity, get_company_idx_metadata
    )
    def demo_peers():
        p1 = demo_company()
        p1["symbol"] = "DEMO1.JK"
        p1["name"] = "Bhinneka Consumer · Illustrative Peer"
        p1["price"] = 1400.0
        p1["shares"] = 6e9
        p2 = demo_company()
        p2["symbol"] = "DEMO2.JK"
        p2["name"] = "Garuda Consumer · Illustrative Peer"
        p2["price"] = 1100.0
        p2["shares"] = 10e9
        return [p1, p2]

    def get_or_fetch_peers(tickers, target_symbol=None):
        clean_target = (target_symbol or "").replace(".JK", "").upper()
        results, errors = [], []
        for t in tickers:
            sym = ticker_symbol(t)
            if sym.replace(".JK", "").upper() == clean_target:
                continue
            try:
                results.append(fetch_company(sym))
            except Exception as e:
                errors.append(f"{t}: {e}")
        return results, errors

try:
    from valuation.report_pdf import generate_valuation_pdf
except ImportError:
    generate_valuation_pdf = None

from valuation.model import (
    get_multiple_exclusion_details,
    Assumptions, BASE_FIELDS, base_check, default_drivers, forecast, dcf, sensitivity,
    relative_values, infer_assumptions, compute_historical_roic, composite_relative_value, blended_valuation,
    evaluate_approach_weights, investment_recommendation, explain_peer_selection
)

def make_assumptions(**kwargs):
    valid_keys = getattr(Assumptions, "__dataclass_fields__", {}).keys()
    filtered = {k: v for k, v in kwargs.items() if k in valid_keys}
    return Assumptions(**filtered)
from valuation.export import workbook
from valuation import storage

st.set_page_config(page_title="Nusa · IDX Valuation Lab", page_icon="◈", layout="wide")
st.markdown("""<style>
/* --- Apple iOS-Inspired Financial Research Design System --- */
:root {
    --ios-text: #1D1D1F;
    --ios-bg: #F5F5F7;
    --ios-surface: #FFFFFF;
    --ios-accent: #087F69;
    --ios-muted: #6E6E73;
    --ios-border: #E5E5EA;
}

html, body, [class*="css"] {
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "SF Pro Display", "Segoe UI", Roboto, Helvetica, Arial, sans-serif !important;
    color: #1D1D1F;
}

.stApp {
    background-color: #F5F5F7;
}

.block-container {
    padding-top: 2.5rem;
    max-width: 1520px;
    padding-bottom: 3.5rem;
}

[data-testid="stSidebar"] {
    background-color: #FFFFFF !important;
    border-right: 1px solid #E5E5EA !important;
}

h1, h2, h3, h4, h5 {
    color: #1D1D1F !important;
    font-weight: 650 !important;
    letter-spacing: -0.02em !important;
}

/* --- iOS Surface Cards & Containers --- */
.ios-card {
    background: #FFFFFF;
    border: 1px solid #E5E5EA;
    border-radius: 14px;
    padding: 18px 20px;
    margin-bottom: 14px;
    box-shadow: 0 1px 4px rgba(0, 0, 0, 0.03);
}

.ios-card-accent {
    background: #FFFFFF;
    border: 1.5px solid #087F69;
    border-radius: 14px;
    padding: 20px 22px;
    margin-bottom: 14px;
    box-shadow: 0 2px 10px rgba(8, 127, 105, 0.06);
}

.ios-section-label {
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #087F69;
    margin-bottom: 4px;
}

.ios-pill {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 3px 10px;
    border-radius: 999px;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.02em;
    border: 1px solid #E5E5EA;
    background: #F5F5F7;
    color: #1D1D1F;
}
.ios-pill-pass { background: #E6F4F1; color: #087F69; border-color: #B7E1D7; }
.ios-pill-warn { background: #FEF3C7; color: #B45309; border-color: #FDE68A; }
.ios-pill-fail { background: #FEE2E2; color: #B91C1C; border-color: #FECACA; }
.ios-pill-info { background: #F5F5F7; color: #1D1D1F; border-color: #D1D1D6; }

/* --- Institutional KPI Metric Card Styling (Zero Ellipsis / Strict Vertical Alignment) --- */
[data-testid="stMetric"] {
    background: #FFFFFF !important;
    border: 1px solid #E5E5EA !important;
    border-radius: 14px !important;
    padding: 16px 18px !important;
    min-height: 124px !important;
    height: 100% !important;
    display: flex !important;
    flex-direction: column !important;
    justify-content: flex-start !important;
    gap: 6px !important;
    box-sizing: border-box !important;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.02) !important;
    transition: border-color 0.15s ease, box-shadow 0.15s ease !important;
}

[data-testid="stMetric"]:hover {
    border-color: #087F69 !important;
    box-shadow: 0 3px 10px rgba(8, 127, 105, 0.06) !important;
}

[data-testid="stMetricLabel"] {
    color: #6E6E73 !important;
    height: 2.85em !important;
    min-height: 2.85em !important;
    display: flex !important;
    align-items: flex-start !important;
    margin-bottom: 2px !important;
    white-space: normal !important;
    overflow: visible !important;
    text-overflow: clip !important;
}

[data-testid="stMetricLabel"],
[data-testid="stMetricLabel"] * {
    color: #6E6E73 !important;
    font-size: 11.5px !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.4px !important;
    white-space: normal !important;
    overflow: visible !important;
    text-overflow: clip !important;
    word-break: break-word !important;
    overflow-wrap: break-word !important;
    line-height: 1.35 !important;
}

[data-testid="stMetricValue"],
[data-testid="stMetricValue"] * {
    white-space: normal !important;
    overflow: visible !important;
    text-overflow: clip !important;
    word-break: normal !important;
    overflow-wrap: break-word !important;
    font-size: clamp(1.18rem, 1.45vw, 1.60rem) !important;
    font-weight: 700 !important;
    color: #1D1D1F !important;
    line-height: 1.2 !important;
    margin: 0 !important;
    font-variant-numeric: tabular-nums !important;
}

[data-testid="stMetricDelta"],
[data-testid="stMetricDelta"] * {
    white-space: normal !important;
    overflow: visible !important;
    text-overflow: clip !important;
    font-size: 0.85rem !important;
}

div[data-testid="column"] {
    display: flex !important;
    flex-direction: column !important;
}

div[data-testid="column"] > div[data-testid="stMetric"],
div[data-testid="column"] > div:has([data-testid="stMetric"]) {
    flex: 1 1 100% !important;
    height: 100% !important;
    display: flex !important;
    flex-direction: column !important;
}

@media (max-width: 1200px) {
    [data-testid="stMetric"] { padding: 12px 14px !important; min-height: 98px !important; }
    [data-testid="stMetricLabel"], [data-testid="stMetricLabel"] * { font-size: 11px !important; }
    [data-testid="stMetricValue"], [data-testid="stMetricValue"] * { font-size: clamp(1.08rem, 1.35vw, 1.42rem) !important; }
}

@media (max-width: 900px) {
    [data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]) { flex-wrap: wrap !important; gap: 12px !important; }
    div[data-testid="column"]:has([data-testid="stMetric"]) { min-width: calc(50% - 12px) !important; flex: 1 1 calc(50% - 12px) !important; }
}

@media (max-width: 600px) {
    div[data-testid="column"]:has([data-testid="stMetric"]) { min-width: 100% !important; flex: 1 1 100% !important; }
}

/* --- Level 3 Primary Navigation: Apple iOS Segmented Control Bar --- */
.st-key-main_nav_container {
    margin-top: 4px !important;
    margin-bottom: 6px !important;
}

/* Shared rounded container for the 3 navigation segments */
.st-key-main_nav_container > div[data-testid="stTabs"] > div[data-baseweb="tab-list"],
div:has(> .st-key-main_nav_container) > div[data-testid="stTabs"] > div[data-baseweb="tab-list"] {
    background-color: #EFEFF4 !important;
    padding: 4px !important;
    border-radius: 14px !important;
    border: 1px solid #E5E5EA !important;
    display: flex !important;
    flex-direction: row !important;
    justify-content: space-between !important;
    gap: 4px !important;
    margin-bottom: 12px !important;
    box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.03) !important;
    max-width: 620px !important;
    width: 100% !important;
}

/* Remove default Streamlit tab underline / highlight bar on primary nav */
.st-key-main_nav_container > div[data-testid="stTabs"] [data-baseweb="tab-border"],
.st-key-main_nav_container > div[data-testid="stTabs"] [data-baseweb="tab-highlight"],
div:has(> .st-key-main_nav_container) > div[data-testid="stTabs"] [data-baseweb="tab-border"],
div:has(> .st-key-main_nav_container) > div[data-testid="stTabs"] [data-baseweb="tab-highlight"] {
    display: none !important;
}

/* Individual navigation segments */
.st-key-main_nav_container > div[data-testid="stTabs"] button[data-baseweb="tab"],
div:has(> .st-key-main_nav_container) > div[data-testid="stTabs"] button[data-baseweb="tab"] {
    flex: 1 1 0 !important;
    text-align: center !important;
    justify-content: center !important;
    align-items: center !important;
    display: inline-flex !important;
    padding: 9px 18px !important;
    height: auto !important;
    min-height: 40px !important;
    border-radius: 10px !important;
    border: 1px solid transparent !important;
    font-size: 14px !important;
    font-weight: 500 !important;
    color: #6E6E73 !important;
    background: transparent !important;
    transition: all 0.16s cubic-bezier(0.16, 1, 0.3, 1) !important;
    box-shadow: none !important;
    margin: 0 !important;
    cursor: pointer !important;
    white-space: nowrap !important;
}

/* Hover feedback on inactive segments */
.st-key-main_nav_container > div[data-testid="stTabs"] button[data-baseweb="tab"]:hover,
div:has(> .st-key-main_nav_container) > div[data-testid="stTabs"] button[data-baseweb="tab"]:hover {
    color: #1D1D1F !important;
    background: rgba(255, 255, 255, 0.6) !important;
}

/* Active Segment (Selected Section) */
.st-key-main_nav_container > div[data-testid="stTabs"] button[data-baseweb="tab"][aria-selected="true"],
div:has(> .st-key-main_nav_container) > div[data-testid="stTabs"] button[data-baseweb="tab"][aria-selected="true"] {
    background-color: #FFFFFF !important;
    color: #1D1D1F !important;
    font-weight: 650 !important;
    border: 1px solid rgba(0, 0, 0, 0.04) !important;
    border-bottom: 2.5px solid #087F69 !important; /* Restrained green accent */
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.06), 0 0.5px 1.5px rgba(0, 0, 0, 0.03) !important;
}

.st-key-main_nav_container > div[data-testid="stTabs"] button[data-baseweb="tab"][aria-selected="true"] p,
div:has(> .st-key-main_nav_container) > div[data-testid="stTabs"] button[data-baseweb="tab"][aria-selected="true"] p {
    color: #1D1D1F !important;
    font-weight: 650 !important;
}

.st-key-main_nav_container > div[data-testid="stTabs"] button[data-baseweb="tab"][aria-selected="false"] p,
div:has(> .st-key-main_nav_container) > div[data-testid="stTabs"] button[data-baseweb="tab"][aria-selected="false"] p {
    color: #6E6E73 !important;
    font-weight: 500 !important;
}

/* --- Level 4: Current Page Context Banner --- */
.page-context-banner {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 9px 15px;
    background: #FFFFFF;
    border: 1px solid #E5E5EA;
    border-left: 3.5px solid #087F69;
    border-radius: 8px;
    margin-bottom: 14px;
    font-size: 13px;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.02);
}

.page-context-title {
    font-weight: 650;
    color: #1D1D1F;
    letter-spacing: -0.01em;
    white-space: nowrap;
}

.page-context-desc {
    color: #6E6E73;
}

@media (max-width: 680px) {
    .st-key-main_nav_container > div[data-testid="stTabs"] > div[data-baseweb="tab-list"],
    div:has(> .st-key-main_nav_container) > div[data-testid="stTabs"] > div[data-baseweb="tab-list"] {
        max-width: 100% !important;
    }
    .st-key-main_nav_container > div[data-testid="stTabs"] button[data-baseweb="tab"],
    div:has(> .st-key-main_nav_container) > div[data-testid="stTabs"] button[data-baseweb="tab"] {
        padding: 7px 10px !important;
        font-size: 12.5px !important;
        min-height: 36px !important;
    }
    .page-context-banner {
        flex-direction: column;
        align-items: flex-start;
        gap: 3px;
        padding: 8px 12px;
    }
}

.eyebrow { color: #087F69; font-size: 11.5px; font-weight: 700; letter-spacing: 1.5px; margin-bottom: 4px; text-transform: uppercase; }
.badge { display: inline-block; background: #E6F4F1; color: #087F69; padding: 4px 12px; border-radius: 999px; font-size: 11.5px; font-weight: 600; border: 1px solid #B7E1D7; }

/* Top-Right Data Retrieval Status Badge */
.retrieval-badge-container {
    display: flex;
    justify-content: flex-end;
    align-items: center;
    width: 100%;
}
.retrieval-badge {
    display: inline-flex;
    flex-direction: column;
    align-items: flex-end;
    text-align: right;
    background: #E6F4F1;
    color: #087F69;
    border: 1px solid #B7E1D7;
    border-radius: 14px;
    padding: 5px 12px;
    font-size: 11.5px;
    font-weight: 500;
    line-height: 1.35;
    white-space: nowrap;
    width: fit-content;
    box-sizing: border-box;
    box-shadow: 0 1px 2px rgba(8, 127, 105, 0.05);
}
.retrieval-badge .badge-source {
    font-size: 11px;
    color: #066352;
    font-weight: 600;
    opacity: 0.95;
}
@media (max-width: 768px) {
    .retrieval-badge {
        font-size: 10.5px;
        padding: 4px 10px;
        border-radius: 12px;
    }
    .retrieval-badge .badge-source {
        font-size: 10px;
    }
    .retrieval-badge .date-full { display: none; }
    .retrieval-badge .date-short { display: inline; }
}
@media (min-width: 769px) {
    .retrieval-badge .date-full { display: inline; }
    .retrieval-badge .date-short { display: none; }
}
.hero { padding: 18px 22px; background: #FFFFFF; color: #1D1D1F; border: 1px solid #E5E5EA; border-radius: 14px; margin: 8px 0 14px; box-shadow: 0 1px 4px rgba(0,0,0,0.03); }
.hero h2 { color: #1D1D1F !important; margin: 0 0 4px; font-size: 1.5rem; }
.hero p { color: #6E6E73; margin: 0; font-size: 0.92rem; }
.small { color: #6E6E73; font-size: 12px; }
button { border-radius: 10px !important; }

/* Model Audit & Sanity Check Strip */
.model-audit-strip {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    background: #FFFFFF;
    border: 1px solid #E5E5EA;
    border-radius: 12px;
    padding: 10px 14px;
    margin: 4px 0 14px;
    align-items: center;
}
.audit-item {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 11.5px;
    color: #1D1D1F;
    background: #F5F5F7;
    border: 1px solid #E5E5EA;
    border-radius: 8px;
    padding: 4px 10px;
}

/* --- Scoped Compact KPI Summary for Valuation Assumptions --- */
.st-key-assump_kpi_wrap {
    margin-bottom: 8px !important;
}

.st-key-assump_kpi_wrap [data-testid="stMetric"] {
    min-height: 94px !important;
    height: 94px !important;
    padding: 12px 16px !important;
    gap: 2px !important;
    justify-content: center !important;
    border-radius: 14px !important;
    background: #FFFFFF !important;
    border: 1px solid #E5E5EA !important;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.02) !important;
    transition: border-color 0.15s ease, box-shadow 0.15s ease !important;
}

.st-key-assump_kpi_wrap [data-testid="stMetric"]:hover {
    border-color: #087F69 !important;
    box-shadow: 0 2px 8px rgba(8, 127, 105, 0.06) !important;
}

.st-key-assump_kpi_wrap [data-testid="stMetricLabel"] {
    height: auto !important;
    min-height: 0 !important;
    margin-bottom: 0px !important;
    line-height: 1.25 !important;
}

.st-key-assump_kpi_wrap [data-testid="stMetricLabel"],
.st-key-assump_kpi_wrap [data-testid="stMetricLabel"] * {
    font-size: 11.5px !important;
    font-weight: 600 !important;
    color: #6E6E73 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.04em !important;
    line-height: 1.25 !important;
}

.st-key-assump_kpi_wrap [data-testid="stMetricValue"] {
    line-height: 1.15 !important;
    margin-top: 2px !important;
}

.st-key-assump_kpi_wrap [data-testid="stMetricValue"],
.st-key-assump_kpi_wrap [data-testid="stMetricValue"] * {
    font-size: 1.55rem !important;
    font-weight: 700 !important;
    color: #1D1D1F !important;
    font-variant-numeric: tabular-nums !important;
    line-height: 1.15 !important;
}

/* --- Outlined Container for Section 04 Scenario Modeling --- */
.st-key-scenario_modeling_box [data-testid="stVerticalBlockBorderWrapper"] {
    background: #FFFFFF !important;
    border: 1px solid #E5E5EA !important;
    border-radius: 14px !important;
    padding: 22px 24px !important;
    margin-top: 16px !important;
    margin-bottom: 20px !important;
    box-shadow: 0 1px 4px rgba(0, 0, 0, 0.02) !important;
}

/* --- Three-Column Assumption Input Symmetry & Alignment --- */
.st-key-assumptions_form_wrap [data-testid="stForm"],
[data-testid="stForm"]:has([data-testid="stFormSubmitButton"]) {
    background: #FFFFFF !important;
    border: 1px solid #E5E5EA !important;
    border-radius: 14px !important;
    padding: 24px 28px !important;
    box-shadow: 0 1px 4px rgba(0, 0, 0, 0.02) !important;
}

.assump-col-header {
    height: 72px;
    min-height: 72px;
    margin-bottom: 12px;
    display: flex;
    flex-direction: column;
    justify-content: flex-start;
}

.assump-col-title {
    font-size: 1.15rem;
    font-weight: 700;
    color: #1D1D1F;
    letter-spacing: -0.015em;
    margin-bottom: 4px;
}

.assump-col-desc {
    font-size: 0.82rem;
    color: #6E6E73;
    line-height: 1.35;
}

.st-key-assumptions_form_wrap [data-testid="stNumberInput"] {
    margin-bottom: 14px !important;
}

.st-key-assumptions_form_wrap div[data-baseweb="input"] {
    border-radius: 10px !important;
    border: 1px solid #E5E5EA !important;
    background: #FFFFFF !important;
    min-height: 42px !important;
    height: 42px !important;
    transition: border-color 0.15s ease, box-shadow 0.15s ease !important;
}

.st-key-assumptions_form_wrap div[data-baseweb="input"]:focus-within {
    border-color: #087F69 !important;
    box-shadow: 0 0 0 2px rgba(8, 127, 105, 0.15) !important;
}

.st-key-assumptions_form_wrap div[data-baseweb="input"] input {
    font-variant-numeric: tabular-nums !important;
    font-size: 13.5px !important;
    font-weight: 500 !important;
    color: #1D1D1F !important;
}

.st-key-assumptions_form_wrap [data-testid="stCheckbox"] {
    margin-top: 4px !important;
    margin-bottom: 12px !important;
}
.audit-item b { color: #1D1D1F; font-weight: 600; }
.audit-dot { width: 7px; height: 7px; border-radius: 50%; display: inline-block; }
.audit-item.passed .audit-dot { background-color: #087F69; }
.audit-item.warning .audit-dot { background-color: #D97706; }
.audit-item.alert .audit-dot { background-color: #DC2626; }

/* Pillar Card Styles */
.pillar-card {
    background: #FFFFFF;
    border: 1px solid #E5E5EA;
    border-radius: 14px;
    padding: 16px 18px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    height: 100%;
    box-sizing: border-box;
    box-shadow: 0 1px 3px rgba(0,0,0,0.02);
}
.pillar-card-featured { border: 1.5px solid #087F69; }
.pillar-tag {
    font-size: 10.5px;
    font-weight: 700;
    letter-spacing: 0.6px;
    text-transform: uppercase;
    padding: 6px 12px;
    border-radius: 8px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    height: 38px;
    min-height: 38px;
    box-sizing: border-box;
    margin-bottom: 10px;
    width: 100%;
}
.pillar-tag-market { background: #F5F5F7; color: #1D1D1F; border: 1px solid #E5E5EA; }
.pillar-tag-dcf { background: #E6F4F1; color: #087F69; border: 1px solid #B7E1D7; }
.pillar-tag-rel { background: #E6F4F1; color: #087F69; border: 1px solid #B7E1D7; }
.pillar-title { font-size: 14.5px; font-weight: 700; color: #1D1D1F; margin-bottom: 2px; }
.pillar-price { font-size: 1.55rem; font-weight: 800; color: #1D1D1F; margin: 4px 0 10px; line-height: 1.15; }
.pillar-unit { font-size: 11px; font-weight: 500; color: #6E6E73; }
.pillar-metrics {
    background: #FFFFFF;
    border: 1px solid #E5E5EA;
    border-radius: 12px;
    padding: 12px 14px;
    margin-top: 8px;
    margin-bottom: 12px;
    display: flex;
    flex-direction: column;
    gap: 8px;
    height: 140px;
    min-height: 140px;
    box-sizing: border-box;
    box-shadow: 0 1px 3px rgba(0,0,0,0.02);
}
.p-row { display: flex; justify-content: space-between; align-items: center; font-size: 12px; line-height: 1.4; color: #6E6E73; height: 22px; }
.p-row b { color: #1D1D1F; font-weight: 600; font-variant-numeric: tabular-nums; }
.pillar-footer { font-size: 11px; color: #6E6E73; border-top: 1px dashed #E5E5EA; padding-top: 8px; margin-top: auto; }

/* --- Scoped Compact KPI Styling for Valuation Synthesis Tri-Pillar Comparison --- */
.st-key-tri_pillar_kpi_wrap [data-testid="stMetric"] {
    min-height: 104px !important;
    height: 106px !important;
    max-height: 110px !important;
    padding: 16px 18px !important;
    display: flex !important;
    flex-direction: column !important;
    justify-content: flex-start !important;
    gap: 4px !important;
    border-radius: 14px !important;
    background: #FFFFFF !important;
    border: 1px solid #E5E5EA !important;
    box-sizing: border-box !important;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.02) !important;
}

.st-key-tri_pillar_kpi_wrap [data-testid="stMetric"]:hover {
    border-color: #087F69 !important;
    box-shadow: 0 2px 8px rgba(8, 127, 105, 0.06) !important;
}

.st-key-tri_pillar_kpi_wrap [data-testid="stMetricLabel"] {
    height: auto !important;
    min-height: 0 !important;
    max-height: none !important;
    margin-bottom: 0px !important;
    display: flex !important;
    align-items: center !important;
    line-height: 1.25 !important;
}

.st-key-tri_pillar_kpi_wrap [data-testid="stMetricLabel"],
.st-key-tri_pillar_kpi_wrap [data-testid="stMetricLabel"] * {
    font-size: 11.5px !important;
    font-weight: 600 !important;
    color: #6E6E73 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.04em !important;
    line-height: 1.25 !important;
}

.st-key-tri_pillar_kpi_wrap [data-testid="stMetricValue"] {
    margin-top: 2px !important;
    line-height: 1.15 !important;
}

.st-key-tri_pillar_kpi_wrap [data-testid="stMetricValue"],
.st-key-tri_pillar_kpi_wrap [data-testid="stMetricValue"] * {
    font-size: clamp(1.30rem, 1.55vw, 1.65rem) !important;
    font-weight: 700 !important;
    color: #1D1D1F !important;
    font-variant-numeric: tabular-nums !important;
    line-height: 1.15 !important;
}

/* Eliminate column vertical stretch on metric inside tri-pillar */
.st-key-tri_pillar_kpi_wrap div[data-testid="column"] > div:has([data-testid="stMetric"]),
.st-key-tri_pillar_kpi_wrap div[data-testid="column"] > div[data-testid="stMetric"] {
    flex: 0 0 auto !important;
    height: auto !important;
}

/* Regulate spacing between KPI card and supporting metric box to 12-16px */
.st-key-tri_pillar_kpi_wrap .pillar-metrics {
    margin-top: 14px !important;
    margin-bottom: 12px !important;
}

.st-key-tri_pillar_kpi_wrap .pillar-tag {
    margin-bottom: 8px !important;
}

@media (max-width: 900px) {
    .st-key-tri_pillar_kpi_wrap [data-testid="stMetric"] {
        min-height: 98px !important;
        height: auto !important;
        padding: 14px 16px !important;
    }
}

/* --- DCF & Relative Valuation Tab: Symmetrical KPI Grid, Equity Bridge & Terminal Economics --- */
.dcf-kpi-grid {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 16px;
    margin: 8px 0 20px;
}
.dcf-kpi-card {
    background: #FFFFFF;
    border: 1px solid #E5E5EA;
    border-radius: 14px;
    padding: 16px 18px;
    min-height: 112px;
    height: 100%;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    box-sizing: border-box;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.02);
    transition: border-color 0.15s ease, box-shadow 0.15s ease;
}
.dcf-kpi-card:hover {
    border-color: #087F69;
    box-shadow: 0 3px 10px rgba(8, 127, 105, 0.06);
}
.dcf-kpi-card-highlight {
    border-top: 3px solid #087F69;
}
.dcf-kpi-label {
    font-size: 11.5px;
    font-weight: 600;
    color: #6E6E73;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    line-height: 1.3;
    min-height: 18px;
    margin-bottom: 6px;
}
.dcf-kpi-value {
    font-size: clamp(1.22rem, 1.45vw, 1.52rem);
    font-weight: 700;
    color: #1D1D1F;
    line-height: 1.2;
    font-variant-numeric: tabular-nums;
    margin-bottom: 8px;
    white-space: nowrap;
}
.dcf-kpi-value-accent {
    color: #087F69;
}
.dcf-kpi-sub {
    font-size: 12px;
    font-weight: 500;
    color: #6E6E73;
    line-height: 1.35;
    font-variant-numeric: tabular-nums;
    margin-top: auto;
    border-top: 1px solid #F2F2F7;
    padding-top: 6px;
}
@media (max-width: 1100px) {
    .dcf-kpi-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
    }
}
@media (max-width: 640px) {
    .dcf-kpi-grid {
        grid-template-columns: 1fr;
    }
}

/* Unified Section Heading for 50:50 Bridge & Terminal Cards */
.dcf-panel-heading {
    font-size: 1.05rem;
    font-weight: 700;
    color: #1D1D1F;
    letter-spacing: -0.015em;
    margin: 0 0 10px 0;
    min-height: 26px;
    display: flex;
    align-items: center;
    justify-content: space-between;
}
.dcf-panel-unit {
    font-size: 11.5px;
    font-weight: 500;
    color: #6E6E73;
}
.dcf-panel-card {
    background: #FFFFFF;
    border: 1px solid #E5E5EA;
    border-radius: 14px;
    padding: 18px 20px;
    box-sizing: border-box;
    box-shadow: 0 1px 4px rgba(0, 0, 0, 0.02);
    margin-bottom: 14px;
}

/* Enterprise-to-Equity Valuation Schedule Table */
.fin-schedule-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
    color: #1D1D1F;
    font-variant-numeric: tabular-nums;
}
.fin-schedule-table th {
    text-align: left;
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: #6E6E73;
    padding: 6px 8px 8px;
    border-bottom: 1.5px solid #E5E5EA;
}
.fin-schedule-table th.num,
.fin-schedule-table td.num {
    text-align: right;
    white-space: nowrap;
}
.fin-schedule-table tr.sec-group td {
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: #087F69;
    background: #F8FAFC;
    padding: 8px 8px 5px;
    border-bottom: 1px solid #E5E5EA;
}
.fin-schedule-table tr.item-row td {
    padding: 7px 8px;
    border-bottom: 1px solid #F2F2F7;
    color: #1D1D1F;
}
.fin-schedule-table tr.subtotal-row td {
    padding: 9px 8px;
    font-weight: 700;
    color: #1D1D1F;
    background: #F5F5F7;
    border-top: 1px solid #D1D1D6;
    border-bottom: 1.5px solid #D1D1D6;
}
.fin-schedule-table tr.final-row td {
    padding: 10px 8px;
    font-weight: 750;
    font-size: 13.5px;
    color: #087F69;
    background: #E6F4F1;
    border-top: 1.5px solid #087F69;
    border-bottom: 2px solid #087F69;
}

/* Terminal Economics Structured Financial Card */
.term-sub-header {
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: #087F69;
    background: #F8FAFC;
    padding: 7px 8px 5px;
    border-bottom: 1px solid #E5E5EA;
    margin-top: 8px;
}
.term-sub-header:first-child {
    margin-top: 0;
}
.term-kv-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 6.5px 8px;
    border-bottom: 1px solid #F2F2F7;
    font-size: 13px;
    color: #1D1D1F;
}
.term-kv-row .t-label {
    color: #1D1D1F;
    font-weight: 450;
}
.term-kv-row .t-val {
    font-weight: 600;
    color: #1D1D1F;
    font-variant-numeric: tabular-nums;
    text-align: right;
}
.term-kv-row.term-highlight {
    background: #F5F5F7;
    font-weight: 700;
    border-top: 1px solid #D1D1D6;
    border-bottom: 1.5px solid #D1D1D6;
}
.term-kv-row.term-highlight .t-label,
.term-kv-row.term-highlight .t-val {
    font-weight: 700;
    color: #1D1D1F;
}
.term-prop-wrap {
    padding: 8px 8px 6px;
    border-bottom: 1px solid #F2F2F7;
}
.term-prop-bar-bg {
    width: 100%;
    height: 8px;
    background: #E5E5EA;
    border-radius: 999px;
    overflow: hidden;
    display: flex;
    margin: 6px 0 5px;
}
.term-prop-bar-fcff {
    background: #94A3B8;
    height: 100%;
}
.term-prop-bar-tv {
    background: #087F69;
    height: 100%;
}
.term-prop-legend {
    display: flex;
    justify-content: space-between;
    font-size: 11.5px;
    color: #6E6E73;
    font-variant-numeric: tabular-nums;
}
.term-val-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 6px;
    padding: 8px 4px 2px;
}
.term-val-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    background: #F8FAFC;
    border: 1px solid #E5E5EA;
    border-radius: 8px;
    padding: 5px 8px;
    font-size: 11.5px;
    color: #1D1D1F;
}
.term-badge-pass {
    font-size: 10px;
    font-weight: 700;
    color: #087F69;
    background: #E6F4F1;
    border: 1px solid #B7E1D7;
    padding: 1px 6px;
    border-radius: 999px;
}
.term-badge-warn {
    font-size: 10px;
    font-weight: 700;
    color: #B45309;
    background: #FEF3C7;
    border: 1px solid #FDE68A;
    padding: 1px 6px;
    border-radius: 999px;
}
.term-badge-fail {
    font-size: 10px;
    font-weight: 700;
    color: #B91C1C;
    background: #FEE2E2;
    border: 1px solid #FECACA;
    padding: 1px 6px;
    border-radius: 999px;
}
.dcf-footnote {
    font-size: 11.5px;
    color: #6E6E73;
    line-height: 1.45;
    margin-top: 10px;
    padding-top: 8px;
    border-top: 1px dashed #E5E5EA;
}

/* --- Overview Key Assumptions & Key Risks Cards --- */
.ov-card {
    background: #FFFFFF;
    border: 1px solid #E5E5EA;
    border-radius: 14px;
    padding: 18px 20px;
    height: 100%;
    min-height: 330px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    box-sizing: border-box;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.02);
    transition: border-color 0.15s ease, box-shadow 0.15s ease;
}
.ov-card:hover {
    border-color: #087F69;
    box-shadow: 0 3px 10px rgba(8, 127, 105, 0.06);
}
.ov-card-head {
    margin-bottom: 10px;
}
.ov-card-title {
    font-size: 15px;
    font-weight: 700;
    color: #1D1D1F;
    margin-top: 2px;
}
.ov-assump-table {
    width: 100%;
    border-collapse: collapse;
    margin-bottom: 12px;
}
.ov-assump-table tr {
    border-bottom: 1px solid #F2F2F7;
    height: 32px;
}
.ov-assump-table tr:last-child {
    border-bottom: none;
}
.ov-assump-table td.ov-label {
    font-size: 12px;
    color: #6E6E73;
    font-weight: 500;
    text-align: left;
    padding: 5px 0;
}
.ov-assump-table td.ov-val {
    font-size: 12px;
    color: #1D1D1F;
    font-weight: 600;
    text-align: right;
    font-variant-numeric: tabular-nums;
    padding: 5px 0;
}
.ov-risk-list {
    display: flex;
    flex-direction: column;
    gap: 9px;
    margin-bottom: 12px;
}
.ov-risk-item {
    background: #F9F9FB;
    border: 1px solid #E5E5EA;
    border-radius: 10px;
    padding: 8px 12px;
    box-sizing: border-box;
}
.ov-risk-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 2px;
}
.ov-risk-title {
    font-size: 12.5px;
    font-weight: 700;
    color: #1D1D1F;
}
.ov-risk-badge {
    font-size: 10px;
    font-weight: 700;
    padding: 1px 7px;
    border-radius: 999px;
    text-transform: uppercase;
    letter-spacing: 0.02em;
}
.ov-risk-badge-amber { background: #FEF3C7; color: #92400E; border: 1px solid #FDE68A; }
.ov-risk-badge-red { background: #FEE2E2; color: #991B1B; border: 1px solid #FECACA; }
.ov-risk-badge-gray { background: #F2F2F7; color: #6E6E73; border: 1px solid #E5E5EA; }
.ov-risk-desc {
    font-size: 11.5px;
    color: #48484A;
    line-height: 1.35;
    margin: 0;
}
.ov-card-nav {
    border-top: 1px dashed #E5E5EA;
    padding-top: 10px;
    margin-top: auto;
    display: flex;
    justify-content: flex-end;
}
.ov-nav-link {
    font-size: 11.5px;
    font-weight: 600;
    color: #087F69;
    cursor: pointer;
    text-decoration: none;
    display: inline-flex;
    align-items: center;
    gap: 4px;
    user-select: none;
}
.ov-nav-link:hover {
    text-decoration: underline;
    color: #065F4E;
}

/* ==========================================================================
   SHARED FINANCIAL TABLE DESIGN SYSTEM (Apple iOS-Inspired Institutional)
   ========================================================================== */

/* Universal Table Wrapper */
.fin-table-container {
    background: #FFFFFF;
    border: 1px solid #E5E5EA;
    border-radius: 12px;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.02);
    overflow: hidden;
    margin: 10px 0 16px;
    width: 100%;
    box-sizing: border-box;
}

.fin-table-header-bar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 10px 14px 8px;
    background: #FAFAFC;
    border-bottom: 1px solid #E5E5EA;
}

.fin-table-title {
    font-size: 13px;
    font-weight: 700;
    color: #1D1D1F;
    letter-spacing: -0.01em;
}

.fin-table-unit {
    font-size: 11px;
    font-weight: 500;
    color: #6E6E73;
    letter-spacing: 0.02em;
}

.fin-table-scroll {
    overflow-x: auto;
    width: 100%;
    scrollbar-width: thin;
    scrollbar-color: #D1D1D6 #F5F5F7;
}

/* Base Financial Table */
.fin-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 12.5px;
    color: #1D1D1F;
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", Roboto, sans-serif;
    line-height: 1.4;
}

/* Header Cells */
.fin-table th {
    background: #F8F9FA;
    color: #6E6E73;
    font-size: 11px;
    font-weight: 650;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    padding: 9px 12px;
    border-bottom: 1.5px solid #E5E5EA;
    white-space: nowrap;
    position: sticky;
    top: 0;
    z-index: 2;
}

.fin-table th.col-label {
    text-align: left;
    min-width: 190px;
}

.fin-table th.col-num {
    text-align: right;
    min-width: 105px;
}

.fin-table th.col-center {
    text-align: center;
}

.fin-table th .th-main {
    font-size: 11.5px;
    font-weight: 700;
    color: #1D1D1F;
}

.fin-table th .th-sub {
    font-size: 10px;
    font-weight: 500;
    color: #8E8E93;
    text-transform: none;
    letter-spacing: 0;
    margin-top: 1px;
}

/* Body Cells */
.fin-table td {
    padding: 7.5px 12px;
    border-bottom: 1px solid #F2F2F7;
    color: #1D1D1F;
    font-size: 12px;
}

.fin-table td.col-label {
    text-align: left;
    font-weight: 500;
    color: #1D1D1F;
}

.fin-table td.col-num {
    text-align: right;
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
}

.fin-table td.col-center {
    text-align: center;
}

.fin-table td.col-dim {
    color: #8E8E93;
}

/* Row Hover */
.fin-table tr:hover td {
    background: #F9FAFB;
}

/* Row Hierarchies */
.fin-table tr.row-major td {
    font-weight: 650;
    color: #1D1D1F;
    background: #FAFAFC;
    border-bottom: 1.5px solid #E5E5EA;
}

.fin-table tr.row-subtotal td {
    font-weight: 700;
    color: #1D1D1F;
    background: #F5F5F7;
    border-top: 1px solid #D1D1D6;
    border-bottom: 1.5px solid #D1D1D6;
}

.fin-table tr.row-final td {
    font-weight: 750;
    font-size: 13px;
    color: #087F69;
    background: #E6F4F1;
    border-top: 1.5px solid #087F69;
    border-bottom: 2px solid #087F69;
}

.fin-table tr.row-category td {
    font-size: 10.5px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: #087F69;
    background: #F8FAFC;
    padding: 8px 12px 6px;
    border-bottom: 1px solid #E5E5EA;
}

/* Badges inside tables */
.fin-badge {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 2px 7px;
    border-radius: 999px;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.02em;
    text-transform: uppercase;
}
.fin-badge-pass { background: #E6F4F1; color: #087F69; border: 1px solid #B7E1D7; }
.fin-badge-warn { background: #FEF3C7; color: #B45309; border: 1px solid #FDE68A; }
.fin-badge-fail { background: #FEE2E2; color: #B91C1C; border: 1px solid #FECACA; }
.fin-badge-info { background: #F2F2F7; color: #6E6E73; border: 1px solid #E5E5EA; }

/* Streamlit Native DataFrame & DataEditor container polish */
div[data-testid="stDataFrame"],
div[data-testid="stDataEditor"] {
    border: 1px solid #E5E5EA !important;
    border-radius: 12px !important;
    overflow: hidden !important;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.02) !important;
    background: #FFFFFF !important;
}

/* Universal Tabs Styling across the entire app */
div[data-testid="stTabs"] > div[data-baseweb="tab-list"] {
    background-color: #EFEFF4 !important;
    padding: 3px !important;
    border-radius: 10px !important;
    border: 1px solid #E5E5EA !important;
    gap: 3px !important;
}
div[data-testid="stTabs"] [data-baseweb="tab-border"],
div[data-testid="stTabs"] [data-baseweb="tab-highlight"] {
    display: none !important;
}
div[data-testid="stTabs"] button[data-baseweb="tab"] {
    border-radius: 8px !important;
    padding: 6px 14px !important;
    font-size: 12px !important;
    font-weight: 500 !important;
    color: #6E6E73 !important;
    background: transparent !important;
    border: none !important;
    transition: all 0.15s ease !important;
}
div[data-testid="stTabs"] button[data-baseweb="tab"]:hover {
    color: #1D1D1F !important;
    background: rgba(255, 255, 255, 0.5) !important;
}
div[data-testid="stTabs"] button[data-baseweb="tab"][aria-selected="true"] {
    background-color: #FFFFFF !important;
    color: #1D1D1F !important;
    font-weight: 650 !important;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06) !important;
    border-bottom: 2px solid #087F69 !important;
}
div[data-testid="stTabs"] button[data-baseweb="tab"][aria-selected="true"] p {
    color: #1D1D1F !important;
    font-weight: 650 !important;
}
div[data-testid="stTabs"] button[data-baseweb="tab"][aria-selected="false"] p {
    color: #6E6E73 !important;
    font-weight: 500 !important;
}
</style>""", unsafe_allow_html=True)


@st.dialog("IDX Valuation Lab · User Guide & Operating Manual", width="large")
def show_user_guide_dialog():
    st.caption("Concise operating manual for MBA students, equity research analysts, and academic assessors.")
    ug_tabs = st.tabs([
        "1–3 · Getting Started & Data",
        "4–7 · Peers, Assumptions & Methods",
        "8–12 · Risks, Decisions & Exports",
    ])
    with ug_tabs[0]:
        st.markdown("#### 1. Getting Started")
        st.write(
            "IDX Valuation Lab is an institutional 3-statement financial modeling and valuation workspace for non-financial companies listed on the Indonesia Stock Exchange (IDX). "
            "Navigate using the three primary sections: **Overview** (executive decision & summary), **Valuation Lab** (7-step interactive modeling workflow), and **Research Report** (audit trail & exports)."
        )
        st.markdown("#### 2. Selecting Companies")
        st.write(
            "Type any 4-letter IDX ticker (e.g., `TLKM`, `ADRO`, `ASII`, `ICBP`, `UNVR`) in the left sidebar and click **Load company**. "
            "The `.JK` suffix is appended automatically. Sector and Sub-Industry classifications are sourced from the official IDX Industrial Classification (IDX-IC) registry, while financial statements are fetched via Yahoo Finance. "
            "By default, the platform automatically initializes with Telkom Indonesia (TLKM) valuation."
        )
        st.markdown("#### 3. Reviewing Financial Data")
        st.write(
            "In **Valuation Lab → Company & data review**, verify the latest common annual fiscal period, reporting currency, reference share price, and diluted shares. "
            "All monetary figures are normalized to **IDR billion** and shares to **billion units**. If a company reports in USD, verify the IDR/USD exchange rate. "
            "You can override any opening account in the interactive table; modified cells are flagged as **User override** while preserving the original reported figure. "
            "Opening Assets must equal Liabilities + Equity (`0.00 bn` discrepancy) before forecasting proceeds."
        )
    with ug_tabs[1]:
        st.markdown("#### 4. Choosing Comparable Peers")
        st.write(
            "In **Valuation Lab → Comparable peers**, the model automatically loads peers from the same IDX Sub-Industry (or 2-digit IDX-IC Industry Group for singleton sub-industries). "
            "Candidates are ranked by financial similarity (EBITDA Margin and Debt-to-Equity distance). You can include/exclude peers via checkboxes, add custom IDX tickers, or reset defaults. "
            "At least **2 valid peers** with positive denominators are required for a multiple to be eligible."
        )
        st.markdown("#### 5. Editing Assumptions")
        st.write(
            "In **Valuation Lab → Valuation assumptions**, assumptions are organized into four groups: "
            "**(1) Operating & Reinvestment**, **(2) Cost of Capital & Terminal**, **(3) Valuation Method Weights**, and **(4) Bear/Base/Bull Scenarios**. "
            "Edit inputs and click **Apply assumptions** to update the 5-year forecast and valuation. Scenario probability and shift inputs below the form update dynamically."
        )
        st.markdown("#### 6. Understanding DCF (5-Year Explicit Forecast)")
        st.write(
            "The intrinsic DCF model projects 3 linked statements over an explicit **5-year horizon** (Years 1–3 operating momentum, Years 4–5 fade toward mature steady state). "
            "Free Cash Flow to the Firm (`FCFF = NOPAT + D&A − CapEx − ΔNWC`) is discounted at WACC. Terminal Value at Year 5 enforces Damodaran's sustainable reinvestment rule (`Reinvestment Rate = g / Terminal ROIC`). "
            "Enterprise Value is bridged to Equity Value by adding opening cash and non-operating assets and subtracting total debt and minority claims."
        )
        st.markdown("#### 7. Understanding Relative Valuation")
        st.write(
            "Relative Valuation evaluates four market multiples (**EV/EBITDA**, **EV/EBIT**, **P/E**, **P/BV**) using either the peer **Median** or **Harmonic Mean**. "
            "Enterprise multiples (`EV/EBITDA`, `EV/EBIT`) are bridged to equity per share using the target company's net debt and claims. Ineligible multiples (<2 valid peers) are automatically excluded and remaining weights normalized to 100%."
        )
    with ug_tabs[2]:
        st.markdown("#### 8. Reviewing Key Risks")
        st.write(
            "In **Valuation Lab → Analyst review**, inspect four structured panels: **Key Assumptions** (inferred vs. user overrides), **Key Risks** (business, financial leverage, macro, valuation sensitivity, and data quality), "
            "**Model Limitations** (reporting age, constant WACC, year-end discounting), and **Model Validation** (`PASS` / `WARNING` / `FAIL` checks)."
        )
        st.markdown("#### 9. Running Valuation")
        st.write(
            "All calculations run deterministically in Python whenever you load a company, apply assumptions, or update peer/scenario controls. "
            "Inspect **DCF & relative valuation** and **Scenario & sensitivity** to audit the 5-year schedules, Enterprise-to-Equity bridge, and WACC vs. Terminal Growth sensitivity matrix."
        )
        st.markdown("#### 10. Reading Recommendations")
        st.write(
            "The central Blended Fair Value combines Expected Scenario-Weighted DCF (default 75% weight) and Relative Valuation (default 25% weight, or 0% if <2 valid peers). "
            "Decision thresholds: **BUY** (`Upside >= +15%`), **HOLD** (`-10% <= Upside < +15%`), **SELL** (`Upside < -10%`), or **NOT ELIGIBLE** if intrinsic equity is negative."
        )
        st.markdown("#### 11. Exporting PDF and Excel")
        st.write(
            "Open **Research Report** (or use the quick export buttons in **Overview**) to download the **PDF Executive Valuation Report** and the **Populated Excel Workbook (.xlsx)** containing the Dashboard, Assumptions, 5-Year Pro-Forma Statements, DCF Waterfall, Sensitivity Matrix, and Peer Multiples with live Excel formulas."
        )
        st.markdown("#### 12. Known Limitations & Troubleshooting")
        st.write(
            "• **Financial Institutions Excluded**: Banks, insurers, and REITs require dedicated DDM/Excess Return models and are blocked by policy.\n"
            "• **Yahoo Finance Coverage**: If Yahoo data is delayed or missing a line item, review the warning in **Company & data review** and enter a verified figure or check the explicit zero-assumption box.\n"
            "• **Cache Refresh**: Use **Clear cached Yahoo data** in the sidebar to force a fresh pull."
        )


@st.cache_data(ttl=3600, show_spinner=False)
def get_company(symbol):
    return fetch_company(symbol)


def activate(company, saved=None):
    if company:
        company = dict(company)
        # Ensure retrieval timestamp is dynamically refreshed on user load
        if not saved and not company.get("demo"):
            company["fetched_at"] = datetime.now(timezone.utc).isoformat()
        elif not company.get("fetched_at"):
            company["fetched_at"] = datetime.now(timezone.utc).isoformat()

        if not company.get("demo") and company.get("symbol"):
            idx_meta = get_company_idx_metadata(company["symbol"])
            if idx_meta:
                company["sector"] = idx_meta["sector"]
                company["industry"] = idx_meta["sub_industry"]
                company["name"] = idx_meta["name"]
    st.session_state.company = company
    st.session_state.revision = st.session_state.get("revision", 0) + 1
    st.session_state.saved_inputs = saved or {}
    if company and company.get("demo"):
        st.session_state.peer_companies = demo_peers()
        st.session_state.peer_errors = []
    else:
        st.session_state.pop("peer_companies", None)
        st.session_state.pop("peer_errors", None)


def pack_company(c):
    packed = {k: v for k, v in c.items() if k not in ("historical", "raw", "price_history")}
    packed["historical"] = c["historical"].to_json(orient="split", date_format="iso")
    packed["raw"] = {name: frame.to_json(orient="split", date_format="iso") for name, frame in c.get("raw", {}).items()}
    if "price_history" in c and isinstance(c["price_history"], (pd.Series, pd.DataFrame)):
        packed["price_history"] = c["price_history"].to_json(orient="split", date_format="iso")
    return packed


def unpack_company(c):
    from io import StringIO
    out = dict(c)
    if not out.get("demo") and out.get("symbol"):
        idx_meta = get_company_idx_metadata(out["symbol"])
        if idx_meta:
            out["sector"] = idx_meta["sector"]
            out["industry"] = idx_meta["sub_industry"]
            out["name"] = idx_meta["name"]
    out["historical"] = pd.read_json(StringIO(c["historical"]), orient="split", convert_axes=False)
    out["raw"] = {name: pd.read_json(StringIO(data), orient="split", convert_axes=False) for name, data in c.get("raw", {}).items()}
    if "price_history" in c and isinstance(c["price_history"], str):
        try:
            ph = pd.read_json(StringIO(c["price_history"]), orient="split")
            out["price_history"] = ph.squeeze("columns") if isinstance(ph, pd.DataFrame) and ph.shape[1] == 1 else ph
        except Exception:
            out["price_history"] = None
    return out


def fmt_idr(val, prefix="Rp ", default="—", allow_negative=False):
    """Format numeric value as IDR string safely handling None, NaN, and infinity."""
    if val is None or not pd.notna(val):
        return default
    try:
        fval = float(val)
        if not math.isfinite(fval):
            return default
        if not allow_negative and fval <= 0:
            return default
        return f"{prefix}{fval:,.0f}"
    except (TypeError, ValueError):
        return default


def fmt_pct(val, decimals=1, signed=False, default="—"):
    """Format numeric value as percentage safely handling None, NaN, and infinity."""
    if val is None or not pd.notna(val):
        return default
    try:
        fval = float(val)
        if not math.isfinite(fval):
            return default
        sign = "+" if signed else ""
        return f"{fval:{sign}.{decimals}%}"
    except (TypeError, ValueError):
        return default


def fmt_shares(val, default="—"):
    """Format share count safely in billions."""
    if val is None or not pd.notna(val):
        return default
    try:
        fval = float(val)
        return f"{fval:,.3f} bn" if math.isfinite(fval) else default
    except (TypeError, ValueError):
        return default


def fmt_multiple(val, decimals=2, suffix="x", default="—"):
    """Format multiple safely (e.g. 12.34x)."""
    if val is None or not pd.notna(val):
        return default
    try:
        fval = float(val)
        return f"{fval:.{decimals}f}{suffix}" if math.isfinite(fval) else default
    except (TypeError, ValueError):
        return default


def chart(fig, ytitle="IDR billion"):
    fig.update_layout(
        template="plotly_white", height=350, margin=dict(l=10, r=10, t=25, b=15),
        font=dict(family="Arial", color="#35504f"), paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)", legend=dict(orientation="h", y=1.12, x=0),
        yaxis_title=ytitle, xaxis_title=None
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="#e4ebe8", zerolinecolor="#d2ded8")
    st.plotly_chart(fig, width="stretch")


if "company" not in st.session_state:
    try:
        init_c = get_company(ticker_symbol("TLKM"))
        if not init_c or init_c.get("historical") is None or init_c["historical"].empty:
            activate(demo_company())
        else:
            activate(init_c)
    except Exception:
        activate(demo_company())

with st.sidebar:
    st.markdown("## ◈ Nusa")
    st.caption("THE IDX VALUATION WORKSPACE")
    with st.form("lookup"):
        typed = st.text_input(
            "IDX ticker",
            placeholder="e.g. TLKM, ADRO, ASII",
            help="Four-character IDX code (e.g. TLKM, ADRO, ICBP, UNVR). The .JK suffix is added automatically."
        )
        submitted = st.form_submit_button("Load company", type="primary", width="stretch")
    if submitted:
        symbol = typed.strip()
        if symbol:
            try:
                with st.spinner(f"Loading annual financial statements for {symbol.upper()}…"):
                    target_sym = ticker_symbol(symbol)
                    try:
                        co = fetch_company(target_sym)
                    except Exception:
                        co = get_company(target_sym)
                    activate(co)
                    st.rerun()
            except Exception as exc:
                st.error(f"Could not load company '{symbol}': {exc}")
        else:
            st.warning("Please enter a valid 4-character IDX ticker (e.g. TLKM, ADRO, ASII).")
    if st.button("User Guide", key="btn_open_user_guide", width="stretch", help="Open the 12-section operating manual and methodology guide"):
        show_user_guide_dialog()
    with st.expander("Saved analyses"):
        saved_list = storage.list_saved()
        if saved_list:
            choice = st.selectbox("Analysis", saved_list, format_func=lambda r: f"{r[1]} · {r[2][:10]}")
            if st.button("Open saved analysis"):
                payload = storage.load(choice[0])
                activate(unpack_company(payload["company"]), payload)
                st.rerun()
        else:
            st.caption("Save your first analysis below after modelling a company.")

c = st.session_state.company
if c and not c.get("demo") and c.get("symbol"):
    idx_meta = get_company_idx_metadata(c["symbol"])
    if idx_meta:
        c["sector"] = idx_meta["sector"]
        c["industry"] = idx_meta["sub_industry"]
        c["name"] = idx_meta["name"]
rev = st.session_state.revision
saved = st.session_state.saved_inputs
key = lambda name: f"{rev}_{name}"

clean_name = clean_company_name(c.get("name", ""))
latest_period_preview = str(c["historical"].columns[-1]) if (c.get("historical") is not None and not c["historical"].empty) else "N/A"
hdr_left, hdr_right = st.columns([3.2, 1.8], vertical_alignment="center")
with hdr_left:
    st.markdown('<div class="eyebrow">NUSA · INDONESIA EQUITY RESEARCH & VALUATION LAB</div>', unsafe_allow_html=True)
    st.markdown(
        f"<h2 style='margin:0 0 2px 0; font-size:1.65rem;'>{escape(clean_name)} "
        f"<span style='color:#6E6E73; font-weight:500; font-size:1.15rem;'>({escape(c.get('symbol', ''))})</span></h2>"
        f"<div style='font-size:0.88rem; color:#6E6E73; line-height:1.45; margin-top:3px;'>"
        f"<div>Sector: <b>{escape(c.get('sector', '—'))}</b> &nbsp;·&nbsp; Sub-Industry: <b>{escape(c.get('industry', '—'))}</b></div>"
        f"<div style='margin-top:2px;'>Fiscal Period: <b>{escape(latest_period_preview)}</b></div>"
        f"</div>",
        unsafe_allow_html=True,
    )
with hdr_right:
    if c["demo"]:
        retrieval_line1_full = retrieval_line1_short = "Offline Benchmark"
        retrieval_line2 = "From : Fictional Dataset"
    else:
        retrieval_line1_full, retrieval_line1_short = format_wib_retrieval(c.get("fetched_at"))
        retrieval_line2 = "From : Yahoo Finance"

    st.markdown(
        f'<div class="retrieval-badge-container">'
        f'<div class="retrieval-badge">'
        f'<div>Retrieved Data: <span class="date-full">{escape(retrieval_line1_full)}</span><span class="date-short">{escape(retrieval_line1_short)}</span></div>'
        f'<div class="badge-source">{escape(retrieval_line2)}</div>'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

if c["demo"]:
    st.info("Fictional demonstration mode active: viewing illustrative financials for Nusantara Consumer Tbk. Load any 4-letter IDX ticker from the left sidebar for live company analysis.")
else:
    if c["sector"] in ("Financial Services", "Financials") or any(x in c["industry"].lower() for x in ("bank", "insurance", "reit")):
        st.warning("This version models non-financial operating companies. Banks, insurers, and REITs need a dedicated valuation model. Choose another company.")
        st.stop()

# Three Main Navigation Sections (Level 3 Primary Architecture)
with st.container(key="main_nav_container"):
    overview, valuation_lab_tab, report_tab = st.tabs([
        "Overview",
        "Valuation Lab",
        "Research Report",
    ])

with valuation_lab_tab:
    st.markdown(
        '<div class="page-context-banner">'
        '<span class="page-context-title">Valuation Lab — Interactive Analysis</span>'
        '<span class="page-context-desc">Review financial data, customize assumptions, select peers, and run valuation scenarios.</span>'
        '</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        "<div style='background:#FFFFFF; border:1px solid #E5E5EA; border-radius:12px; padding:10px 16px; margin-bottom:10px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;'>"
        "<div><span class='ios-section-label'>VALUATION LAB WORKFLOW</span> "
        "<span style='font-size:12.5px; color:#6E6E73; margin-left:8px;'>1. Data Review &rarr; 2. Comparable Peers &rarr; 3. Assumptions &rarr; 4. Analyst Review &rarr; 5. DCF &amp; Relative &rarr; 6. Scenarios &rarr; 7. Interpretation</span></div>"
        "<span class='ios-pill ios-pill-info'>Non-restrictive flow · All inputs preserved across steps</span>"
        "</div>",
        unsafe_allow_html=True,
    )
    data_tab, peers_tab, assumptions_tab, analyst_review_tab, dcf_tab, scenario_tab, final_interp_tab = st.tabs([
        "Company & data review",
        "Comparable peers",
        "Valuation assumptions",
        "Analyst review",
        "DCF & relative valuation",
        "Scenario & sensitivity",
        "Final interpretation",
    ])

with data_tab:
    st.subheader("Company & Data Review")
    fx = 1.0
    if c["financial_currency"] != "IDR":
        suggested_fx = float(c.get("suggested_fx", 16000.0 if c["financial_currency"] == "USD" else 1.0))
        st.warning(f"Reported financial currency: {c['financial_currency'] or 'unknown'}. Live indicative exchange rate: {suggested_fx:,.2f} IDR/{c['financial_currency']}.")
        fx = st.number_input("IDR per 1 reporting-currency unit", min_value=0., value=float(saved.get("fx", suggested_fx)), key=key("fx"), format="%.4f")
    if c["price_currency"] != "IDR":
        st.warning("Market price currency is not verified as IDR. Enter an independently verified IDR price below.")
    historical = c["historical"] * fx
    period = str(historical.columns[-1])
    first_year = pd.Timestamp(period).year + 1

    # Market & Reference Observation Inputs placed prominently alongside company profile
    col1, col2 = st.columns(2)
    with col1:
        default_shares_val = (c.get("shares") or 0) / BILLION
        if default_shares_val <= 0:
            raw_dict = c.get("raw", {})
            bs_raw = raw_dict.get("Balance sheet")
            inc_raw = raw_dict.get("Income statement")
            if bs_raw is not None and not bs_raw.empty:
                for row in ("OrdinarySharesNumber", "ShareIssued"):
                    if row in bs_raw.index and not bs_raw.loc[row].dropna().empty:
                        default_shares_val = float(bs_raw.loc[row].dropna().iloc[-1]) / BILLION
                        break
            if default_shares_val <= 0 and inc_raw is not None and not inc_raw.empty:
                for row in ("DilutedAverageShares", "BasicAverageShares"):
                    if row in inc_raw.index and not inc_raw.loc[row].dropna().empty:
                        default_shares_val = float(inc_raw.loc[row].dropna().iloc[-1]) / BILLION
                        break

        shares_init = float(saved.get("shares", default_shares_val if default_shares_val > 0 else 1.0))
        shares = st.number_input(
            "Current / diluted shares outstanding (billions)",
            min_value=0.000001,
            value=max(0.000001, shares_init),
            key=key("shares"),
            format="%.6f",
            help="Diluted share count in billions. Sourced from audited balance sheet / latest market filing."
        )
    with col2:
        price = st.number_input("Reference market price (IDR/share)", min_value=0., value=float(saved.get("price", c["price"] or 0)), key=key("price"))

    obs_mkt_cap = (price * shares) if (price and shares) else 0.0
    mc1, mc2, mc3, mc4 = st.columns(4)
    mc1.metric("Selected Ticker", c.get("symbol", "—"))
    mc2.metric("Latest Audited Period", f"FY {period}")
    mc3.metric("Observed Market Cap", f"Rp {obs_mkt_cap:,.1f} bn" if obs_mkt_cap > 0 else "Not available")
    mc4.metric("Statement Currency", f"{c.get('financial_currency', 'IDR')} ({'1.0x' if fx == 1.0 else f'FX {fx:,.0f}'})")
    st.caption("Current shares reflect a no-future-dilution baseline; override with diluted shares if applicable. Other current assets/liabilities are treated as operating unless reclassified.")

    st.markdown(f"#### Historical Annual Financial Statements · Audited through {period}")
    hist_view_tabs = st.tabs([
        "All Core Accounts",
        "Income Statement",
        "Balance Sheet",
        "Cash Flow & Capital",
    ])
    inc_keys = [k for k in ("revenue", "cogs", "opex", "da", "interest", "tax", "net_income") if k in historical.index]
    bs_keys = [k for k in ("cash", "ar", "inventory", "other_ca", "ppe", "other_assets", "ap", "other_cl", "short_debt", "long_debt", "other_liabilities", "equity") if k in historical.index]
    cf_keys = [k for k in ("ebit", "ebitda", "cfo", "capex", "minority_interest", "nonoperating_assets") if k in historical.index]

    with hist_view_tabs[0]:
        df_all = historical.loc[[k for k in BASE_FIELDS if k in historical.index]].rename(index=BASE_FIELDS)
        cat_map = {
            BASE_FIELDS.get("revenue", "Revenue"): "1. Income Statement Line Items",
            BASE_FIELDS.get("cash", "Cash and cash equivalents"): "2. Balance Sheet Assets",
            BASE_FIELDS.get("ap", "Trade accounts payable"): "3. Balance Sheet Liabilities & Equity",
        }
        hl_rows = [
            BASE_FIELDS.get("revenue", "Revenue"),
            BASE_FIELDS.get("net_income", "Net income"),
            BASE_FIELDS.get("ppe", "Net property, plant and equipment"),
            BASE_FIELDS.get("equity", "Total common equity"),
        ]
        sub_rows = [BASE_FIELDS.get("net_income", "Net income"), BASE_FIELDS.get("equity", "Total common equity")]
        st.markdown(
            render_apple_table(
                df_all,
                title=f"{clean_company_name(c.get('name', 'Company'))} · Consolidated Historical Accounts",
                unit_label=f"Unit: IDR billion · Audited through FY{period}",
                is_transposed_periods=True,
                highlight_rows=hl_rows,
                subtotal_rows=sub_rows,
                category_rows=cat_map,
            ),
            unsafe_allow_html=True,
        )
    with hist_view_tabs[1]:
        df_inc = historical.loc[inc_keys].rename(index=BASE_FIELDS)
        st.markdown(
            render_apple_table(
                df_inc,
                title=f"{clean_company_name(c.get('name', 'Company'))} · Historical Income Statement",
                unit_label=f"Unit: IDR billion · Audited through FY{period}",
                is_transposed_periods=True,
                highlight_rows=[BASE_FIELDS.get("revenue", "Revenue"), BASE_FIELDS.get("net_income", "Net income")],
                subtotal_rows=[BASE_FIELDS.get("net_income", "Net income")],
            ),
            unsafe_allow_html=True,
        )
    with hist_view_tabs[2]:
        df_bs = historical.loc[bs_keys].rename(index=BASE_FIELDS)
        cat_map_bs = {
            BASE_FIELDS.get("cash", "Cash and cash equivalents"): "Assets",
            BASE_FIELDS.get("ap", "Trade accounts payable"): "Liabilities & Equity",
        }
        st.markdown(
            render_apple_table(
                df_bs,
                title=f"{clean_company_name(c.get('name', 'Company'))} · Historical Balance Sheet",
                unit_label=f"Unit: IDR billion · Audited through FY{period}",
                is_transposed_periods=True,
                highlight_rows=[
                    BASE_FIELDS.get("cash", "Cash and cash equivalents"),
                    BASE_FIELDS.get("ppe", "Net property, plant and equipment"),
                    BASE_FIELDS.get("equity", "Total common equity"),
                ],
                subtotal_rows=[BASE_FIELDS.get("equity", "Total common equity")],
                category_rows=cat_map_bs,
            ),
            unsafe_allow_html=True,
        )
    with hist_view_tabs[3]:
        if cf_keys:
            cf_labels = BASE_FIELDS | {
                "ebit": "EBIT",
                "ebitda": "EBITDA",
                "cfo": "Operating cash flow",
                "capex": "Capital expenditure",
                "minority_interest": "Minority interest",
                "nonoperating_assets": "Non-operating assets",
            }
            df_cf = historical.loc[cf_keys].rename(index=cf_labels)
            st.markdown(
                render_apple_table(
                    df_cf,
                    title=f"{clean_company_name(c.get('name', 'Company'))} · Cash Flow & Capital Profile",
                    unit_label=f"Unit: IDR billion · Audited through FY{period}",
                    is_transposed_periods=True,
                    highlight_rows=["EBITDA", "Operating cash flow", "Capital expenditure"],
                    subtotal_rows=["Operating cash flow"],
                ),
                unsafe_allow_html=True,
            )
        else:
            st.caption("Supplemental cash-flow rows are available in the raw statement expanders below.")

    source_base = historical.loc[list(BASE_FIELDS), historical.columns[-1]]
    base_values = saved.get("base", source_base.to_dict())

    # Build structured mapping review rows
    parsed_prov = []
    type_list = []
    for k in BASE_FIELDS:
        is_ov = (
            pd.notna(base_values.get(k))
            and pd.notna(source_base[k])
            and abs(float(base_values.get(k)) - float(source_base[k])) > 1e-4
        )
        raw_p = (
            "User override"
            if is_ov
            else ("Saved/user input" if saved else c["provenance"].get(f"{period}:{k}", "Illustrative"))
        )
        p_type, p_detail = parse_mapping_provenance(raw_p, is_override=is_ov)
        type_list.append(p_type)
        parsed_prov.append(p_detail)

    review = pd.DataFrame(
        {
            "Key": [k for k in BASE_FIELDS],
            "Account": [BASE_FIELDS[k] for k in BASE_FIELDS],
            "Reported": [source_base[k] for k in BASE_FIELDS],
            "Value": [base_values.get(k) for k in BASE_FIELDS],
            "Type": type_list,
            "Source": parsed_prov,
        },
        index=list(BASE_FIELDS),
    )

    direct_count = sum(1 for t in type_list if t == "Direct")
    calc_count = sum(1 for t in type_list if t == "Calculated")
    override_count = sum(1 for t in type_list if "Override" in t)

    st.markdown("#### Review and Correct Opening Inputs (FY Base Period)")
    st.caption("Edit the 'Model input · IDR bn' column to correct missing or misclassified source items. Original provider figures remain preserved in 'Reported · IDR bn'.")
    st.markdown(
        f"""
        <div class="fin-table-header-bar" style="border-radius: 12px 12px 0 0; margin-top: 10px;">
            <div class="fin-table-title">Opening Balance Sheet &amp; Operating Mapping · FY{period}</div>
            <div class="fin-table-unit">
                {direct_count} Direct · {calc_count} Calculated · {override_count} Override(s) | All figures in IDR billion
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    edited = st.data_editor(
        review,
        hide_index=True,
        disabled=["Key", "Account", "Reported", "Type", "Source"],
        column_config={
            "Key": st.column_config.TextColumn(
                label="Key",
                help="Standardized technical model account key",
                width="small",
            ),
            "Account": st.column_config.TextColumn(
                label="Account",
                help="Financial statement line item",
                width="medium",
            ),
            "Reported": st.column_config.NumberColumn(
                label="Reported (IDR bn)",
                help="Audited provider figure sourced directly from annual filings",
                format="%,.2f",
                width="small",
            ),
            "Value": st.column_config.NumberColumn(
                label="Model Input (IDR bn)",
                help="Active base opening figure used by valuation model. Click cell to edit or override.",
                format="%,.2f",
                width="small",
            ),
            "Type": st.column_config.TextColumn(
                label="Mapping Type",
                help="Derivation classification: Direct reported, Calculated residual, or User override",
                width="small",
            ),
            "Source": st.column_config.TextColumn(
                label="Source / Mapping",
                help="Taxonomy mapping rule or derivation formula",
                width="large",
            ),
        },
        height=450,
        width="stretch",
        key=key("base_editor"),
    )
    override_accounts = [
        BASE_FIELDS[k] for k in BASE_FIELDS
        if pd.notna(edited.loc[k, "Value"]) and pd.notna(source_base[k]) and abs(float(edited.loc[k, "Value"]) - float(source_base[k])) > 1e-4
    ]
    if override_accounts:
        st.info(f"User override active on {len(override_accounts)} opening account(s): {', '.join(override_accounts)}.")
    missing = [k for k in BASE_FIELDS if pd.isna(edited.loc[k, "Value"])]
    accept_missing = False
    if missing:
        st.warning("Missing opening accounts: " + ", ".join(BASE_FIELDS[k] for k in missing))
        accept_missing = st.checkbox("I reviewed the missing accounts and explicitly assume they are zero", key=key("missing"))
    b = {k: float(edited.loc[k, "Value"]) if pd.notna(edited.loc[k, "Value"]) else 0. for k in BASE_FIELDS}
    if abs(base_check(b)) > .01:
        st.error(f"Opening balance sheet difference: IDR {base_check(b):,.2f} bn. Correct the input accounts above; the model never inserts an artificial balancing plug.")
    else:
        st.success(f"Opening balance sheet verified: Assets = Liabilities + Equity (0.00 bn discrepancy).")

    for name, raw in c["raw"].items():
        with st.expander(f"Raw source · {name} · {c['financial_currency'] or 'currency unverified'} units"):
            st.dataframe(raw, width="stretch")

if fx <= 0 or (missing and not accept_missing):
    with overview:
        st.warning("Open Valuation Lab → Company & data review and complete the missing inputs or currency conversion to unlock the forecast.")
    st.stop()


def inferred_assumptions():
    return infer_assumptions(historical, b, c)


applied_saved = st.session_state.get(key("applied_assumptions"))
if applied_saved:
    initial = make_assumptions(**applied_saved)
elif saved.get("assumptions"):
    initial = make_assumptions(**saved["assumptions"])
else:
    initial = inferred_assumptions()

with assumptions_tab:
    st.subheader("Valuation assumptions & methodology lab")
    st.caption("Review, customize, and stress-test the three fundamental pillars of the valuation model. Changes update all connected statements, DCF cash flows, and relative valuation bridges.")

    # Reserve the top slot for compact KPI metrics
    metric_slot = st.container(key="assump_kpi_wrap")
    st.markdown('<div style="height:1px; background:#E5E5EA; margin:12px 0 16px 0;"></div>', unsafe_allow_html=True)

    with st.container(key="assumptions_form_wrap"):
        with st.form(key("assumptions")):
            fields = {}

            def pct(label, field, lo=0., hi=100., help=None):
                fields[field] = st.number_input(
                    label,
                    min_value=float(lo),
                    max_value=float(hi),
                    value=float(getattr(initial, field) * 100),
                    step=.5,
                    key=key(field),
                    help=help
                ) / 100

            col_op, col_macro, col_policy = st.columns([1, 1, 1], gap="medium")

            with col_op:
                st.markdown(
                    '<div class="assump-col-header">'
                    '<div class="assump-col-title">01 · Operating model</div>'
                    '<div class="assump-col-desc">Revenue growth, operating margins, reinvestment, and capital intensity.</div>'
                    '</div>',
                    unsafe_allow_html=True,
                )
                # Calculate raw historical revenue CAGR for dynamic tooltip disclosure
                cagr_hist = None
                if historical is not None and not historical.empty and "revenue" in historical.index:
                    s_rev = historical.loc["revenue"].dropna()
                    if len(s_rev) >= 4 and s_rev.iloc[-4] > 0 and s_rev.iloc[-1] > 0:
                        cagr_hist = (float(s_rev.iloc[-1]) / float(s_rev.iloc[-4])) ** (1.0 / 3.0) - 1.0
                    elif len(s_rev) >= 2 and s_rev.iloc[-2] > 0 and s_rev.iloc[-1] > 0:
                        cagr_hist = (float(s_rev.iloc[-1]) / float(s_rev.iloc[-2])) - 1.0

                sec_raw = (c.get("sector") or "") if c else ""
                ind_raw = (c.get("industry") or "") if c else ""
                is_cyclical = (
                    sec_raw in ("Energy", "Basic Materials") or 
                    any(x in ind_raw.lower() for x in ("coal", "mining", "metal", "oil", "gas", "farm products", "agriculture", "plantation", "crop", "cooper"))
                )
                archetype = getattr(initial, "growth_archetype", None)
                if not archetype:
                    if is_cyclical and cagr_hist is not None and cagr_hist < 0.02:
                        archetype = "commodity_cycle"
                    elif not is_cyclical and cagr_hist is not None and cagr_hist < 0.0:
                        archetype = "macro_mature"
                    else:
                        archetype = "organic_cagr"

                if archetype == "commodity_cycle":
                    growth_help = (
                        f"Normalized to {initial.growth:.1%} via Damodaran Cyclical Commodity framework (trailing audited 3-year CAGR was {cagr_hist:.1%} "
                        f"due to commodity price cycle trough). In Years 4–5, revenue growth smoothly transitions toward Year 5 mature growth ({initial.mature_growth:.1%})."
                    )
                elif archetype == "macro_mature":
                    growth_help = (
                        f"Normalized to {initial.growth:.1%} via Indonesia Macro & Mature Industry framework (trailing audited 3-year CAGR was {cagr_hist:.1%} "
                        f"due to mature market saturation/price competition, rather than commodity cycles). Anchored to Bank Indonesia's long-term macro inflation baseline (2.50%). "
                        f"In Years 4–5, revenue growth smoothly transitions toward Year 5 mature growth ({initial.mature_growth:.1%})."
                    )
                else:
                    growth_help = (
                        f"Anchored to audited 3-year historical revenue CAGR ({initial.growth:.1%}). "
                        f"In Years 4–5, revenue growth smoothly transitions toward Year 5 mature growth ({initial.mature_growth:.1%})."
                    )

                pct(
                    "Growth · years 1–3 (%)", "growth", -50, 100,
                    help=growth_help
                )
                pct(
                    "Growth · year 5 (%)", "mature_growth", -50, 50,
                    help="Target steady-state revenue growth rate at Year 5. In Year 4, growth smoothly transitions (2/3 initial + 1/3 mature) toward this level, reflecting competitive fade toward long-term GDP growth."
                )
                pct(
                    "EBIT margin · years 1–3 (%)", "ebit_margin", -50, 80,
                    help="Operating profit margin before interest and taxes: EBIT / Revenue. Represents core business operating profitability. Inferred baseline is derived from the latest audited annual statement."
                )
                pct(
                    "EBIT margin · year 5 (%)", "mature_margin", -50, 80,
                    help="Target operating margin at Year 5. In Year 4, the model smoothly transitions (2/3 initial + 1/3 mature) toward this steady-state level, reflecting long-term competitive convergence or margin expansion."
                )
                pct(
                    "Gross margin (%)", "gross_margin", 1, 100,
                    help="Direct operating profitability after Cost of Goods Sold (COGS): (Revenue - COGS) / Revenue. In this model, cash OpEx is dynamically derived as the residual (Revenue - COGS - D&A - EBIT). Higher gross margin expands operating cushion."
                )
                pct(
                    "Corporate tax rate (%)", "tax_rate", 0, 60,
                    help="Inferred baseline is 22.0% (Indonesian statutory corporate rate under UU HPP No. 7/2021). The model includes Damodaran Net Operating Loss (NOL) carryforward protection."
                )
                pct(
                    "Capex / revenue (%)", "capex_pct", 0, 100,
                    help="Annual capital expenditure as a percentage of revenue: CapEx / Revenue. Inferred baseline uses the 4-year statistical median (2022–2025) to smooth out lumpy expansion projects and reflect ongoing maintenance and productive asset replacement."
                )
                pct(
                    "D&A / opening fixed assets (%)", "depreciation_rate", 0, 100,
                    help="Accounting amortization rate of net fixed assets: D&A / Opening Net PP&E. Governs how fast physical plant, machinery, and equipment depreciate on the balance sheet and are added back to operating cash flow in FCFF."
                )
                pct(
                    "Non-cash working capital / revenue (%)", "nwc_pct", -50, 80,
                    help="Damodaran Non-Cash Working Capital ratio: ((AR + Inventory + Other CA) - (AP + Other CL)) / Revenue. Measures operational liquidity tied up in the business. Working capital is driven by non-cash NWC % of revenue instead of turnover days."
                )
                pct(
                    "Minimum cash / revenue (%)", "minimum_cash_pct", 0, 100,
                    help="Minimum operational liquidity cushion required for day-to-day operations (default 2.0% of revenue). Shortfalls below this floor trigger liquidity revolver financing in the cash flow roll-forward."
                )

                # Preserve background cash roll-forward fields
                fields["ar_days"] = float(initial.ar_days)
                fields["inventory_days"] = float(initial.inventory_days)
                fields["ap_days"] = float(initial.ap_days)
                fields["other_ca_pct"] = float(initial.other_ca_pct)
                fields["other_cl_pct"] = float(initial.other_cl_pct)
                fields["dividend_payout"] = float(initial.dividend_payout)
                fields["annual_repayment"] = float(initial.annual_repayment)

            with col_macro:
                st.markdown(
                    '<div class="assump-col-header">'
                    '<div class="assump-col-title">02 · Macro & WACC</div>'
                    '<div class="assump-col-desc">Damodaran ERP, Indonesia CRP, JKSE regression beta, and capital structure.</div>'
                    '</div>',
                    unsafe_allow_html=True,
                )
                pct(
                    "Risk-free rate (%)", "risk_free", 0, 30,
                    help="Indonesian 10-Year Government Benchmark Bond yield (FR series) as of Dec 31, 2025 (6.64%). Sovereign baseline risk-free rate used in CAPM."
                )
                pct(
                    "Mature market ERP (%)", "mature_equity_premium", 0, 20,
                    help="Damodaran published NYU Stern mature equity risk premium (4.60%). Baseline equity risk compensation for mature markets (S&P 500 baseline)."
                )
                m_erp = fields.get("mature_equity_premium", initial.mature_equity_premium)
                c_crp = fields.get("country_risk_premium", initial.country_risk_premium)
                pct(
                    "Indonesia country risk premium (CRP) (%)", "country_risk_premium", 0, 20,
                    help=f"Damodaran published Indonesia Country Risk Premium ({c_crp*100:.2f}%), based on sovereign rating (Baa2/BBB) and relative equity volatility. Total Indonesia ERP = Mature ERP ({m_erp*100:.2f}%) + CRP ({c_crp*100:.2f}%) = {((m_erp + c_crp)*100):.2f}%."
                )
                fields["equity_premium"] = fields["mature_equity_premium"]
                fields["beta"] = st.number_input("Levered beta", min_value=-2.0, max_value=4., value=float(initial.beta), step=.05, key=key("beta"), help="Derived from 5Y monthly regression vs ^JKSE with Blume mean-reversion adjustment.")
                pct(
                    "Pre-tax borrowing cost (%)", "debt_rate", 0, 50,
                    help="Effective pre-tax debt borrowing rate (Kd = Interest Expense / Total Debt). In accordance with Damodaran currency consistency rules, Kd is floored at sovereign Rf + 150 bps corporate spread if reported rates reflect offshore foreign-currency (e.g. USD) obligations."
                )
                pct(
                    "Target debt / capital (%)", "debt_weight", 0, 95,
                    help="Target capital structure debt weight (D / (D + E)). Inferred from latest balance sheet book debt vs market capitalization."
                )
                override = st.checkbox(
                    "Override calculated WACC",
                    value=initial.wacc_override is not None,
                    key=key("override"),
                    help="By default, WACC is automatically calculated from market risk, beta, and debt costs. Check this box if you want to bypass the formula and manually type your own discount rate (e.g. an internal 12% fund hurdle rate)."
                )
                custom_wacc = st.number_input(
                    "WACC override (%)",
                    min_value=.1,
                    max_value=60.,
                    value=float((initial.wacc_override or initial.wacc) * 100),
                    step=.25,
                    key=key("custom_wacc"),
                    help="Custom discount rate applied to the DCF valuation when 'Override calculated WACC' is checked above, then submitted via 'Apply assumptions'."
                )
                fields["wacc_override"] = custom_wacc / 100 if override else None

            with col_policy:
                st.markdown(
                    '<div class="assump-col-header">'
                    '<div class="assump-col-title">03 · Valuation policy</div>'
                    '<div class="assump-col-desc">Multi-approach weighting, terminal parameters, and balance sheet claims bridge.</div>'
                    '</div>',
                    unsafe_allow_html=True,
                )
                pct(
                    "Terminal growth (%)", "terminal_growth", 0, 15,
                    help="Damodaran perpetual growth rate in Gordon Growth Terminal Value. Default 2.50% aligns with Bank Indonesia long-term central inflation target. Strictly bounded below Indonesian GDP ceiling (4.00%) and WACC."
                )
                hist_roic_val = compute_historical_roic(historical, b, tax_rate=initial.tax_rate)
                reinv_terminal = (initial.terminal_growth / initial.terminal_roic) if initial.terminal_roic > 0 else 0.0
                pct(
                    "Terminal ROIC (%)", "terminal_roic", .1, 100,
                    help=(
                        f"Calibrated from audited historical median ROIC ({hist_roic_val*100:.1f}%) fading to {initial.terminal_roic*100:.1f}% "
                        f"below median as growth decelerates to perpetuity (WACC {initial.wacc*100:.1f}%). "
                        f"Implied sustainable reinvestment rate: {reinv_terminal*100:.1f}% (g / ROIC)."
                    )
                )
                pct(
                    "Valuation weight · DCF (%)", "dcf_weight", 0, 100,
                    help="Weight assigned to DCF (FCFF) intrinsic valuation in the blended fair value recommendation. Default 75% aligns with institutional anchor principle."
                )
                pct(
                    "Valuation weight · Relative (%)", "relative_weight", 0, 100,
                    help="Weight assigned to Comparable Peers relative valuation in the blended fair value. Default 25% provides an empirical market cross-check when peer similarity criteria are met."
                )
                fields["other_claims"] = st.number_input("Minorities / other equity claims (IDR bn)", min_value=0., value=float(initial.other_claims), key=key("claims"), help="Deducts reported minority interests (NCI) from EV to bridge to Equity Value.")
                fields["nonoperating_assets"] = st.number_input("Additional non-operating assets (IDR bn)", min_value=0., value=float(initial.nonoperating_assets), key=key("nonop"), help="Adds non-operating investments / associates to EV.")

            st.divider()
            applied = st.form_submit_button("Apply assumptions", type="primary", use_container_width=True)
    base_a = make_assumptions(**fields)
    if applied:
        st.session_state[key("applied_assumptions")] = asdict(base_a)

    # Populate top metric_slot with ACTIVE assumptions (base_a)
    with metric_slot:
        m_r1_1, m_r1_2, m_r1_3 = st.columns(3, gap="small")
        m_r1_1.metric("Calculated WACC", f"{base_a.wacc:.2%}")
        m_r1_2.metric("Cost of Equity", f"{base_a.cost_of_equity:.2%}")
        m_r1_3.metric("Borrowing Cost (Kd)", f"{base_a.debt_rate:.2%}")

        m_r2_1, m_r2_2, m_r2_3 = st.columns(3, gap="small")
        m_r2_1.metric("Debt Weight", f"{base_a.debt_weight:.0%}")
        m_r2_2.metric("Initial Growth (Y1–3)", f"{base_a.growth:.1%}")
        m_r2_3.metric("EBIT Margin (Y1–3)", f"{base_a.ebit_margin:.1%}")

    # Section 04 wrapped in bordered outline container
    with st.container(key="scenario_modeling_box", border=True):
        st.markdown('<div id="section-04-scenario-modeling"></div>', unsafe_allow_html=True)
        st.markdown("#### 04 · Scenario modeling & stress testing")
        st.caption("Simulates macroeconomic and operational regimes across Bear, Base, and Bull cases. Deviations and probabilities are governed by institutional framework rules.")

        # Scenario Probabilities
        st.markdown("##### Scenario Probability Weighting")

        p_col1, p_col2, p_col3 = st.columns(3)
        with p_col1:
            p_bear_def = float(st.session_state.get(key("prob_bear"), saved.get("prob_bear", getattr(initial, "prob_bear", 0.25)) * 100))
            p_bear_val = st.number_input(
                "Bear probability (%)",
                min_value=20.0, max_value=25.0, value=p_bear_def, step=0.5,
                key=key("prob_bear"),
                help="Probability allocated to Bear downturn scenario (governed range: 20.0% – 25.0%). Default 25.0%."
            )

        with p_col2:
            p_base_def = float(st.session_state.get(key("prob_base"), saved.get("prob_base", getattr(initial, "prob_base", 0.50)) * 100))
            p_base_val = st.number_input(
                "Base probability (%)",
                min_value=50.0, max_value=60.0, value=p_base_def, step=0.5,
                key=key("prob_base"),
                help="Probability allocated to Base consensus scenario (governed range: 50.0% – 60.0%). Default 50.0%."
            )

        with p_col3:
            p_bull_def = float(st.session_state.get(key("prob_bull"), saved.get("prob_bull", getattr(initial, "prob_bull", 0.25)) * 100))
            p_bull_val = st.number_input(
                "Bull probability (%)",
                min_value=20.0, max_value=25.0, value=p_bull_def, step=0.5,
                key=key("prob_bull"),
                help="Probability allocated to Bull expansion scenario (governed range: 20.0% – 25.0%). Default 25.0%."
            )

        total_prob = p_bear_val + p_base_val + p_bull_val
        if not math.isclose(total_prob, 100.0, abs_tol=0.01):
            st.warning(f"Total probability is {total_prob:.1f}%. It must sum to exactly 100.0% for accurate expected value weighting.")

        with st.expander("Scenario Calibration (Bear & Bull Deviations)", expanded=True):
            st.caption("Customize specific deviations for Bull and Bear scenarios across operating, macro discount, and reinvestment drivers.")

            sc_c1, sc_c2 = st.columns(2)
            with sc_c1:
                st.markdown("##### Bear Scenario (Economic Downturn)")
                b_g_def = float(st.session_state.get(key("bear_growth_shift"), saved.get("bear_growth_shift", getattr(initial, "bear_growth_shift", -0.02)) * 100))
                b_g_val = st.number_input(
                    "Revenue growth shift (%)",
                    value=b_g_def, step=0.25, key=key("bear_growth_shift"),
                    help="Percentage points added to revenue growth in Bear scenario."
                )

                b_m_def = float(st.session_state.get(key("bear_margin_shift"), saved.get("bear_margin_shift", getattr(initial, "bear_margin_shift", -0.02)) * 100))
                b_m_val = st.number_input(
                    "EBIT margin shift (%)",
                    value=b_m_def, step=0.25, key=key("bear_margin_shift"),
                    help="Percentage points added to EBIT margin in Bear scenario."
                )

                b_w_def = float(st.session_state.get(key("bear_wacc_shift"), saved.get("bear_wacc_shift", getattr(initial, "bear_wacc_shift", 0.005)) * 100))
                b_w_val = st.number_input(
                    "WACC shift (%)",
                    value=b_w_def, step=0.10, key=key("bear_wacc_shift"),
                    help="Credit spread / risk premium expansion in distress."
                )

                b_tg_def = float(st.session_state.get(key("bear_g_shift"), saved.get("bear_g_shift", getattr(initial, "bear_g_shift", -0.005)) * 100))
                b_tg_val = st.number_input(
                    "Terminal growth shift (%)",
                    value=b_tg_def, step=0.10, key=key("bear_g_shift"),
                    help="Long-term economic slowdown."
                )

                b_r_def = float(st.session_state.get(key("bear_roic_shift"), saved.get("bear_roic_shift", getattr(initial, "bear_roic_shift", -0.010)) * 100))
                b_r_val = st.number_input(
                    "Terminal ROIC shift (%)",
                    value=b_r_def, step=0.25, key=key("bear_roic_shift"),
                    help="Competitive moat erosion under economic pressure."
                )

                b_re_def = float(st.session_state.get(key("bear_reinvest_shift"), saved.get("bear_reinvest_shift", getattr(initial, "bear_reinvest_shift", 0.010)) * 100))
                b_re_val = st.number_input(
                    "CapEx & NWC drag (%)",
                    value=b_re_def, step=0.25, key=key("bear_reinvest_shift"),
                    help="Working capital stretch and capital intensity burden in downturn."
                )

            with sc_c2:
                st.markdown("##### Bull Scenario (Economic Expansion)")
                u_g_def = float(st.session_state.get(key("bull_growth_shift"), saved.get("bull_growth_shift", getattr(initial, "bull_growth_shift", 0.02)) * 100))
                u_g_val = st.number_input(
                    "Revenue growth shift (%)",
                    value=u_g_def, step=0.25, key=key("bull_growth_shift"),
                    help="Percentage points added to revenue growth in Bull scenario."
                )

                u_m_def = float(st.session_state.get(key("bull_margin_shift"), saved.get("bull_margin_shift", getattr(initial, "bull_margin_shift", 0.02)) * 100))
                u_m_val = st.number_input(
                    "EBIT margin shift (%)",
                    value=u_m_def, step=0.25, key=key("bull_margin_shift"),
                    help="Percentage points added to EBIT margin in Bull scenario."
                )

                u_w_def = float(st.session_state.get(key("bull_wacc_shift"), saved.get("bull_wacc_shift", getattr(initial, "bull_wacc_shift", -0.005)) * 100))
                u_w_val = st.number_input(
                    "WACC shift (%)",
                    value=u_w_def, step=0.10, key=key("bull_wacc_shift"),
                    help="Risk premium compression in economic expansion."
                )

                u_tg_def = float(st.session_state.get(key("bull_g_shift"), saved.get("bull_g_shift", getattr(initial, "bull_g_shift", 0.005)) * 100))
                u_tg_val = st.number_input(
                    "Terminal growth shift (%)",
                    value=u_tg_def, step=0.10, key=key("bull_g_shift"),
                    help="Higher sustainable economic growth."
                )

                u_r_def = float(st.session_state.get(key("bull_roic_shift"), saved.get("bull_roic_shift", getattr(initial, "bull_roic_shift", 0.010)) * 100))
                u_r_val = st.number_input(
                    "Terminal ROIC shift (%)",
                    value=u_r_def, step=0.25, key=key("bull_roic_shift"),
                    help="Enhanced returns on capital during expansion."
                )

                u_re_def = float(st.session_state.get(key("bull_reinvest_shift"), saved.get("bull_reinvest_shift", getattr(initial, "bull_reinvest_shift", -0.010)) * 100))
                u_re_val = st.number_input(
                    "CapEx & NWC boost (%)",
                    value=u_re_def, step=0.25, key=key("bull_reinvest_shift"),
                    help="Operational and capital efficiency improvement."
                )

    a = replace(
        base_a,
        prob_bear=p_bear_val / 100.0,
        prob_base=p_base_val / 100.0,
        prob_bull=p_bull_val / 100.0,
        bear_growth_shift=b_g_val / 100.0,
        bear_margin_shift=b_m_val / 100.0,
        bear_wacc_shift=b_w_val / 100.0,
        bear_g_shift=b_tg_val / 100.0,
        bear_roic_shift=b_r_val / 100.0,
        bear_reinvest_shift=b_re_val / 100.0,
        bull_growth_shift=u_g_val / 100.0,
        bull_margin_shift=u_m_val / 100.0,
        bull_wacc_shift=u_w_val / 100.0,
        bull_g_shift=u_tg_val / 100.0,
        bull_roic_shift=u_r_val / 100.0,
        bull_reinvest_shift=u_re_val / 100.0,
    )

    # Macro convergence & GDP ceiling warning (Damodaran Boundary)
    if a.terminal_growth > 0.040:
        st.warning(
            f"⚠️ **Damodaran Macro Ceiling Alert**: Terminal growth ({a.terminal_growth:.1%}) exceeds the sustainable "
            f"Indonesian nominal GDP growth ceiling (4.00%). In academic valuation theory, steady-state firms cannot "
            f"permanently outgrow the broader macroeconomy into perpetuity."
        )
    elif a.terminal_growth >= a.wacc:
        st.error(
            f"⛔ **Convergence Violation**: Terminal growth ({a.terminal_growth:.2%}) must be strictly less than WACC "
            f"({a.wacc:.2%}) to avoid mathematical singularity in Gordon Growth Terminal Value."
        )

    # Phased Horizon Academic Justification Cards
    with st.expander("Academic Rationale & 5-Year Phased Horizon", expanded=False):
        p_col1, p_col2, p_col3 = st.columns(3)
        with p_col1:
            st.markdown("##### Phase 1 · Operational Momentum (Y1–3)")
            st.caption(
                "Reflects near-term backlog execution, historical 3-year revenue CAGR momentum, and reinvestment capacity. "
                "Operating margins and CapEx intensity are anchored to audited multi-year medians."
            )
        with p_col2:
            st.markdown("##### Phase 2 · Convergence (Y4–5)")
            st.caption(
                "Abnormal competitive advantages (economic moats) gradually dissipate under market competition. "
                "Growth rates and operating margins smoothly fade toward macroeconomic equilibrium."
            )
        with p_col3:
            st.markdown("##### Phase 3 · Steady State (Perpetuity Year 6+)")
            st.caption(
                "Perpetual growth is bounded by Bank Indonesia's central inflation target (2.50%) with zero perpetual "
                "volume expansion. Terminal reinvestment is disciplined by sustainable ROIC (g / ROIC)."
            )

# Derive 5-year drivers directly from Valuation Assumptions
drivers = default_drivers(a, first_year)

try:
    f = forecast(b, a, first_year, drivers)
except ValueError as exc:
    with overview:
        st.error(str(exc))
    st.stop()

try:
    result = dcf(f, b, a, shares)
    grid = sensitivity(f, b, a, shares)
except ValueError as exc:
    result = None
    grid = pd.DataFrame()
    with overview:
        st.warning(f"DCF unavailable: {exc}. You can still review the financial forecast.")

scenario_rows = []
base_dcf_price = result["price"] if result and pd.notna(result.get("price")) else None

scenario_configs = [
    {
        "label": "Bear",
        "prob": getattr(a, "prob_bear", 0.25),
        "growth_shift": getattr(a, "bear_growth_shift", -0.02),
        "margin_shift": getattr(a, "bear_margin_shift", -0.02),
        "wacc_shift": getattr(a, "bear_wacc_shift", 0.005),
        "g_shift": getattr(a, "bear_g_shift", -0.005),
        "roic_shift": getattr(a, "bear_roic_shift", -0.010),
        "reinvest_shift": getattr(a, "bear_reinvest_shift", 0.010),
    },
    {
        "label": "Base",
        "prob": getattr(a, "prob_base", 0.50),
        "growth_shift": 0.0,
        "margin_shift": 0.0,
        "wacc_shift": 0.0,
        "g_shift": 0.0,
        "roic_shift": 0.0,
        "reinvest_shift": 0.0,
    },
    {
        "label": "Bull",
        "prob": getattr(a, "prob_bull", 0.25),
        "growth_shift": getattr(a, "bull_growth_shift", 0.02),
        "margin_shift": getattr(a, "bull_margin_shift", 0.02),
        "wacc_shift": getattr(a, "bull_wacc_shift", -0.005),
        "g_shift": getattr(a, "bull_g_shift", 0.005),
        "roic_shift": getattr(a, "bull_roic_shift", 0.010),
        "reinvest_shift": getattr(a, "bull_reinvest_shift", -0.010),
    },
]

for cfg in scenario_configs:
    label = cfg["label"]
    sd = drivers.copy()
    sd["Growth %"] += cfg["growth_shift"] * 100
    sd["EBIT margin %"] += cfg["margin_shift"] * 100

    if cfg["reinvest_shift"] != 0:
        sd["Capex / sales %"] = sd["Capex / sales %"].apply(lambda x: max(0.5, x + cfg["reinvest_shift"] * 100))

    sa = a
    if cfg["wacc_shift"] != 0 or cfg["g_shift"] != 0 or cfg["roic_shift"] != 0 or cfg["reinvest_shift"] != 0:
        scen_wacc = max(0.04, min(0.35, a.wacc + cfg["wacc_shift"]))
        scen_g = max(0.005, min(scen_wacc - 0.005, a.terminal_growth + cfg["g_shift"]))
        scen_roic = max(scen_g + 0.01, a.terminal_roic + cfg["roic_shift"])
        scen_nwc = (a.nwc_pct if a.nwc_pct is not None else 0.10) + cfg["reinvest_shift"]
        sa = replace(
            a,
            wacc_override=scen_wacc,
            terminal_growth=scen_g,
            terminal_roic=scen_roic,
            nwc_pct=scen_nwc
        )

    try:
        sf = forecast(b, sa, first_year, sd)
        sr = dcf(sf, b, sa, shares)
        scen_price = sr["price"]
        upside = ((scen_price / base_dcf_price) - 1.0) if (base_dcf_price and base_dcf_price > 0 and pd.notna(scen_price)) else 0.0
        row_dict = {
            "Scenario": label,
            "Probability": cfg["prob"],
            "Value / share": scen_price,
            "Upside / Downside": f"{upside:+.1%}" if label != "Base" else "Base case",
            "Year 5 revenue": sf.iloc[-1].revenue,
            "Year 5 EBIT": sf.iloc[-1].ebit,
            "WACC": sa.wacc,
            "Terminal growth": sa.terminal_growth,
            "Terminal ROIC": sa.terminal_roic,
        }
        scenario_rows.append(row_dict)
    except Exception:
        row_dict = {
            "Scenario": label,
            "Value / share": float("nan"),
            "Upside / Downside": "—",
            "Year 5 revenue": float("nan"),
            "Year 5 EBIT": float("nan"),
            "WACC": sa.wacc,
            "Terminal growth": sa.terminal_growth,
            "Terminal ROIC": sa.terminal_roic,
        }
        scenario_rows.append(row_dict)

# Probability-weighted expected DCF valuation across scenarios
norm_probs = a.normalized_scenario_probabilities()
prices_by_scenario = {r["Scenario"]: r["Value / share"] for r in scenario_rows if pd.notna(r.get("Value / share"))}
if len(prices_by_scenario) == 3 and base_dcf_price and base_dcf_price > 0:
    expected_dcf_price = sum(prices_by_scenario[scen] * norm_probs.get(scen, 0.0) for scen in ["Bear", "Base", "Bull"])
else:
    expected_dcf_price = base_dcf_price

# Prepare peer context and blended valuation
target_ebitda = b["revenue"] - b["cogs"] - b["opex"]
target_profile = dict(
    symbol=c["symbol"],
    revenue=b["revenue"],
    ebitda=target_ebitda,
    ebitda_margin=(target_ebitda / b["revenue"]) if b["revenue"] > 0 else 0.15,
    der=((b["short_debt"] + b["long_debt"]) / max(1.0, b.get("equity", 1.0))),
    industry=c.get("industry", "Unknown"),
    sector=c.get("sector", "Unknown"),
)
default_peer_tickers = ", ".join(get_default_peers_for_ticker(c["symbol"], c.get("industry")))

peer_rows = []
relative = pd.DataFrame()
rel_price = float("nan")
rel_breakdown = {}

# Multiple aggregator choice (Median or Harmonic mean)
rel_agg_choice = st.session_state.get(key("rel_agg_choice"), "Median")

# Configurable multiple weights (default: EV/EBITDA 35%, EV/EBIT 20%, P/E 25%, P/BV 20%)
w_ebitda = float(st.session_state.get(key("w_mult_ebitda"), 35.0))
w_ebit = float(st.session_state.get(key("w_mult_ebit"), 20.0))
w_pe = float(st.session_state.get(key("w_mult_pe"), 25.0))
w_pbv = float(st.session_state.get(key("w_mult_pbv"), 20.0))
mult_weights_raw = {
    "EV / EBITDA": w_ebitda,
    "EV / EBIT": w_ebit,
    "P / E": w_pe,
    "P / BV": w_pbv
}
tot_mult_w = sum(mult_weights_raw.values())
if tot_mult_w > 0:
    mult_weights_norm = {k: v / tot_mult_w for k, v in mult_weights_raw.items()}
else:
    mult_weights_norm = {k: 0.25 for k in mult_weights_raw}

# Track active target ticker to ensure peer set stays aligned with target issuer
clean_current_target = c["symbol"].replace(".JK", "").upper()
if st.session_state.get("_active_target_ticker") != clean_current_target:
    st.session_state["_active_target_ticker"] = clean_current_target
    if not c.get("demo"):
        st.session_state.pop("peer_companies", None)
        st.session_state.pop("peer_errors", None)

# Auto-initialize peers in session state if missing
if "peer_companies" not in st.session_state or st.session_state.peer_companies is None:
    if c.get("demo"):
        st.session_state.peer_companies = demo_peers()
        st.session_state.peer_errors = []
    elif saved.get("peers"):
        st.session_state.peer_companies = []
    else:
        # Pre-load suggested peers
        suggested_init = get_default_peers_for_ticker(c["symbol"], c.get("industry"))
        pcs_init, errs_init = get_or_fetch_peers(suggested_init[:4], target_symbol=c["symbol"])
        st.session_state.peer_companies = pcs_init
        st.session_state.peer_errors = errs_init

active_peers = st.session_state.get("peer_companies", [])
if active_peers:
    for pc in active_peers:
        if pc and not pc.get("demo") and pc.get("symbol"):
            p_idx = get_company_idx_metadata(pc["symbol"])
            if p_idx:
                pc["sector"] = p_idx["sector"]
                pc["industry"] = p_idx["sub_industry"]
                pc["name"] = p_idx["name"]
        if st.session_state.get(key(f"include_{pc['symbol']}"), True):
            try:
                p_fx = fx if pc.get("financial_currency") == "USD" else 1.0
                peer_rows.append(peer_record(pc, period, fx=p_fx))
            except ValueError:
                pass
elif saved.get("peers"):
    peer_rows = saved["peers"]

if peer_rows and shares > 0:
    target = dict(
        revenue=b["revenue"],
        ebit=b["revenue"] - b["cogs"] - b["opex"] - b["da"],
        ebitda=target_ebitda,
        net_income=b["net_income"],
        book_equity=max(0.0, b.get("equity", 0.0) - a.other_claims),
    )
    relative = relative_values(peer_rows, target, b["cash"], b["short_debt"] + b["long_debt"], shares, a.other_claims, a.nonoperating_assets)
    exclusion_info = get_multiple_exclusion_details(peer_rows)
    if len(peer_rows) >= 2:
        rel_price, rel_breakdown = composite_relative_value(
            relative,
            metrics=("EV / EBITDA", "EV / EBIT", "P / E", "P / BV"),
            case=rel_agg_choice,
            weights=mult_weights_norm,
            min_peers=2,
            return_breakdown=True
        )

dcf_p = expected_dcf_price if (expected_dcf_price and pd.notna(expected_dcf_price)) else (result["price"] if result else None)
blended_price = blended_valuation(dcf_p, rel_price, a.dcf_weight, a.relative_weight)
effective_price = blended_price if pd.notna(blended_price) else dcf_p

is_dcf_ineligible = (dcf_p is not None and pd.notna(dcf_p) and dcf_p <= 0)
exclusion_info = get_multiple_exclusion_details(peer_rows) if 'exclusion_info' not in locals() else exclusion_info
approach_eval = evaluate_approach_weights(target_profile, peer_rows, a.dcf_weight, a.relative_weight)
rec = investment_recommendation(price, effective_price, dcf_price=dcf_p)

# Pre-compute shared validation states, provenance checks, and risk/limitation facts (Single Source of Truth)
bs_diff = base_check(b)
fc_bs_max_diff = float(f.balance_check.abs().max()) if f is not None and "balance_check" in f.columns else 0.0
funding = float(f.funding.sum()) if f is not None and "funding" in f.columns else 0.0
term_share = float(result["terminal_share"]) if (result and "terminal_share" in result) else 0.0
from datetime import date as _date_cls
statement_age_days = (_date_cls.today() - pd.Timestamp(period).date()).days if not c.get("demo") else 0
has_neg_residual_bs = any(b[k] < 0 for k in ("other_ca", "other_cl", "other_assets", "other_liabilities"))

mkt_cap = (price * shares) if (price and shares) else None
pe_ratio = (mkt_cap / b["net_income"]) if (mkt_cap and b.get("net_income") and b["net_income"] > 0) else None
pe_str = f"{pe_ratio:.1f}x" if pe_ratio else "—"
tot_debt = b.get("short_debt", 0.0) + b.get("long_debt", 0.0)
ev_market = (mkt_cap + tot_debt - b.get("cash", 0.0)) if mkt_cap else None
evebitda_ratio = (ev_market / target_ebitda) if (ev_market and target_ebitda and target_ebitda > 0) else None
evebitda_str = f"{evebitda_ratio:.1f}x" if evebitda_ratio else "—"

bear_price = next((x["Value / share"] for x in scenario_rows if x["Scenario"] == "Bear" and pd.notna(x["Value / share"])), None)
bull_price = next((x["Value / share"] for x in scenario_rows if x["Scenario"] == "Bull" and pd.notna(x["Value / share"])), None)
base_dcf_price = result["price"] if result else None

q25 = composite_relative_value(relative[relative["Case"] == "Lower quartile"].replace("Lower quartile", "Median")) if (not relative.empty and "Case" in relative.columns and "Lower quartile" in relative["Case"].values) else (rel_price * 0.85 if pd.notna(rel_price) else None)
q75 = composite_relative_value(relative[relative["Case"] == "Upper quartile"].replace("Upper quartile", "Median")) if (not relative.empty and "Case" in relative.columns and "Upper quartile" in relative["Case"].values) else (rel_price * 1.15 if pd.notna(rel_price) else None)
q25_str = f"Rp {q25:,.0f}" if pd.notna(q25) else "—"
q75_str = f"Rp {q75:,.0f}" if pd.notna(q75) else "—"

range_candidates = [v for v in (bear_price, bull_price, q25, q75, effective_price) if v is not None and pd.notna(v) and v > 0]
fair_value_low = min(range_candidates) if range_candidates else None
fair_value_high = max(range_candidates) if range_candidates else None
fair_value_range_str = f"Rp {fair_value_low:,.0f} – Rp {fair_value_high:,.0f}" if (fair_value_low and fair_value_high) else "Not available"

# Pre-build PDF and Excel bytes once for reuse across Overview, Research Report, and Sidebar
pdf_report_bytes = None
excel_bytes = None
try:
    if generate_valuation_pdf is not None:
        pdf_report_bytes = generate_valuation_pdf(
            company=c,
            assumptions=a,
            dcf_result=result,
            scenario_rows=scenario_rows,
            relative_df=relative,
            rel_breakdown=rel_breakdown,
            rel_price=rel_price,
            blended_price=blended_price,
            effective_price=effective_price,
            expected_dcf_price=expected_dcf_price,
            rec=rec,
            approach_eval=approach_eval,
            peer_rows=peer_rows,
        )
    if result:
        excel_bytes = workbook(
            company=c,
            historical=historical,
            base=b,
            assumptions=a,
            drivers=drivers,
            forecast=f,
            result=result,
            grid=grid,
            peers=peer_rows,
            relative=relative,
            expected_dcf_price=expected_dcf_price,
            rel_price=rel_price,
            blended_price=blended_price,
            rec=rec,
            scenario_rows=scenario_rows,
            mult_weights=mult_weights_norm,
            rel_breakdown=rel_breakdown,
        )
except Exception as _export_prep_err:
    pass

with overview:
    st.markdown(
        '<div class="page-context-banner">'
        '<span class="page-context-title">Overview — Investment Snapshot</span>'
        '<span class="page-context-desc">Understand the company, market price, fair value, and investment recommendation.</span>'
        '</div>',
        unsafe_allow_html=True,
    )
    st.subheader("Executive Valuation Overview")

    # 1. Investment Summary & Decision Hero Row (Level 1 — Decision)
    rec_up_val = rec.get("upside")
    rec_mos_val = rec.get("margin_of_safety")
    rec_up_str = fmt_pct(rec_up_val, signed=True)
    rec_mos_str = fmt_pct(rec_mos_val)
    upside_str = (
        f"""<span style="font-size: 14px; color: #B91C1C;">Capital Structure: <b>Negative Intrinsic Equity (Insolvent / Restructuring Risk)</b></span>"""
        if rec["rating"] == "NOT ELIGIBLE" else
        f"""<span style="font-size: 15px; color: #1D1D1F;">Implied Upside: <b>{rec_up_str}</b> &nbsp;|&nbsp; Margin of Safety: <b>{rec_mos_str}</b> &nbsp;|&nbsp; Fair-Value Range: <b>{fair_value_range_str}</b></span>"""
    )
    rec_col, dl_col = st.columns([3.8, 1.4], vertical_alignment="center")
    with rec_col:
        st.markdown(
            f"""<div class="ios-card" style="border-left: 5px solid {rec['color']}; margin: 0 0 12px;">
            <span style="font-size: 11px; font-weight: 700; letter-spacing: 1.1px; color: {rec['color']}; text-transform: uppercase;">LEVEL 1 DECISION · INVESTMENT RECOMMENDATION &amp; CENTRAL FAIR VALUE</span>
            <div style="display: flex; align-items: baseline; gap: 16px; margin: 6px 0 4px; flex-wrap: wrap;">
                <span style="font-size: 24px; font-weight: 800; color: {rec['color']};">{rec['rating']}</span>
                {upside_str}
            </div>
            <div style="font-size: 13px; color: #6E6E73;">{rec['summary']}</div>
            </div>""",
            unsafe_allow_html=True,
        )
    with dl_col:
        if pdf_report_bytes is not None:
            st.download_button(
                label="Download PDF Report",
                data=pdf_report_bytes,
                file_name=f"{c['symbol'].replace('.JK', '')}_Valuation_Report.pdf",
                mime="application/pdf",
                key=key("dl_pdf_banner"),
                type="primary",
                use_container_width=True,
            )
        if excel_bytes is not None:
            st.download_button(
                label="Export Excel (.xlsx)",
                data=excel_bytes,
                file_name=f"{c['symbol'].replace('.JK', '')}_Valuation.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key=key("dl_excel_banner"),
                use_container_width=True,
            )

    if is_dcf_ineligible:
        ev_val = result.get("enterprise_value", 0.0) if result else 0.0
        st.warning(
            f"**Valuation Eligibility Notice: {clean_name} ({c['symbol']}) is Not Eligible for Automated Valuation**\n\n"
            f"Automated DCF modeling is suspended for this ticker under trailing audited statements because:\n\n"
            f"1. **Severe Balance Sheet Debt Overhang**: Total balance sheet debt (Rp {tot_debt:,.1f} bn) exceeds operating enterprise value (Rp {ev_val:,.1f} bn), resulting in underwater intrinsic equity ({fmt_idr(dcf_p, default='N/A')}/share).\n"
            f"2. **Pre-Revenue Capital Project Timing**: Debt was drawn for multi-billion dollar construction (e.g. smelter expansion), but expanded commercial revenues are not yet online in historical data.\n"
            f"3. **Missing D&A Reporting**: Source statements report zero D&A, penalizing cash flows by the entire capex without non-cash depreciation addbacks.\n\n"
            f"*Valuing this company requires excessive speculative forecasting (forward production ramp-up schedules and commodity pricing) rather than reliable fundamental extrapolation.*"
        )

    # 2. Core KPI Cards (Comfortable 3-Block Density — Zero Truncation)
    kpi_r1_1, kpi_r1_2, kpi_r1_3 = st.columns(3)
    kpi_r1_1.metric(
        "Central Blended Fair Value / Share",
        fmt_idr(effective_price, default="Not eligible" if is_dcf_ineligible else "Not available"),
        delta=f"{rec['upside']:+.1%} vs market" if (rec["rating"] != "NOT ELIGIBLE" and rec.get("upside") is not None and pd.notna(rec.get("upside"))) else None,
        help="Weighted synthesis of Scenario-Weighted DCF and Relative Peer Valuation using effective approach weights.",
    )
    kpi_r1_2.metric(
        "Observed Reference Market Price",
        fmt_idr(price, default="Not available"),
        help=f"Reference market share price (IDR/share). Market Cap: {fmt_idr(mkt_cap, prefix='Rp ', default='—')} bn." if mkt_cap else "Reference market price in IDR.",
    )
    kpi_r1_3.metric(
        "Fair-Value Range (Bear–Bull / P25–P75)",
        fair_value_range_str,
        help="Consolidated valuation range spanning DCF Bear/Bull scenarios and Relative Valuation interquartile (P25–P75) bounds.",
    )

    # 3. Model Health & Sanity Audit Strip (Relocated directly under 3 KPI cards)
    bs_status = "passed" if abs(bs_diff) <= 0.01 else "alert"
    bs_label = "PASS · Balanced (0.00 bn)" if abs(bs_diff) <= 0.01 else f"FAIL · Discrepancy ({bs_diff:,.2f} bn)"
    curr_status = "passed" if c.get("financial_currency") == "IDR" else ("warning" if fx > 0 else "alert")
    curr_label = "PASS · IDR Verified" if c.get("financial_currency") == "IDR" else f"WARNING · {c.get('financial_currency')} (FX {fx:,.0f})"
    tg_status = "passed" if (a.terminal_growth <= 0.040 and a.terminal_growth < a.wacc) else ("alert" if a.terminal_growth >= a.wacc else "warning")
    tg_label = f"PASS · {a.terminal_growth*100:.2f}% (<= GDP)" if a.terminal_growth <= 0.040 else f"WARNING · {a.terminal_growth*100:.2f}% (> GDP)"
    peer_status = "passed" if len(peer_rows) >= 2 else "warning"
    peer_label = f"PASS · {len(peer_rows)} Active Peers" if len(peer_rows) >= 2 else f"WARNING · {len(peer_rows)}/2 Peers (100% DCF)"
    solv_status = "alert" if is_dcf_ineligible else "passed"
    solv_label = "PASS · Solvent (Equity > 0)" if not is_dcf_ineligible else "ALERT · Underwater Intrinsic Equity"

    st.markdown(
        f"""<div class="model-audit-strip" style="margin: 12px 0 18px;">
            <span style="font-size: 11px; font-weight: 700; color: #6E6E73; text-transform: uppercase; letter-spacing: 0.5px; margin-right: 4px;">Model Status &amp; Checks:</span>
            <div class="audit-item {bs_status}"><span class="audit-dot"></span><span>Balance Sheet: <b>{bs_label}</b></span></div>
            <div class="audit-item {curr_status}"><span class="audit-dot"></span><span>Currency: <b>{curr_label}</b></span></div>
            <div class="audit-item {tg_status}"><span class="audit-dot"></span><span>Terminal g: <b>{tg_label}</b></span></div>
            <div class="audit-item {peer_status}"><span class="audit-dot"></span><span>Peers: <b>{peer_label}</b></span></div>
            <div class="audit-item {solv_status}"><span class="audit-dot"></span><span>Capital Structure: <b>{solv_label}</b></span></div>
        </div>""",
        unsafe_allow_html=True,
    )

    # 4. Tri-Pillar Method Comparison (Level 2 — Explanation)
    st.markdown("### Valuation Synthesis · Tri-Pillar Method Comparison")
    with st.container(key="tri_pillar_kpi_wrap"):
        p_col1, p_col2, p_col3 = st.columns(3)
        with p_col1:
            st.markdown('<div class="pillar-tag pillar-tag-market"><span>PILLAR 1 · OBSERVED MARKET</span><span>0% WEIGHT</span></div>', unsafe_allow_html=True)
            st.metric(
                "Reference price",
                fmt_idr(price, default="Not available"),
                help="Current reference market trading price on the Indonesia Stock Exchange (IDX).",
            )
            st.markdown(
                f"""<div class="pillar-metrics">
                    <div class="p-row"><span>Market Cap</span><b>{fmt_idr(mkt_cap, prefix='Rp ', default='—')} bn</b></div>
                    <div class="p-row"><span>Trailing P/E</span><b>{pe_str}</b></div>
                    <div class="p-row"><span>EV / EBITDA</span><b>{evebitda_str}</b></div>
                    <div class="p-row"><span>Diluted Shares</span><b>{fmt_shares(shares)}</b></div>
                </div>""",
                unsafe_allow_html=True,
            )

        with p_col2:
            st.markdown(f'<div class="pillar-tag pillar-tag-dcf"><span>PILLAR 2 · INTRINSIC DCF ANCHOR</span><span>{approach_eval["dcf_weight"]:.0%} WEIGHT</span></div>', unsafe_allow_html=True)
            st.metric(
                "DCF value / share",
                fmt_idr(dcf_p, default="Not eligible" if is_dcf_ineligible else "Check assumptions") if (dcf_p and dcf_p > 0) else ("Not eligible" if is_dcf_ineligible else "Check assumptions"),
                help=f"Probability-weighted expected DCF value across Bear ({norm_probs.get('Bear', 0.25):.0%}), Base ({norm_probs.get('Base', 0.50):.0%}), and Bull ({norm_probs.get('Bull', 0.25):.0%}) scenarios. Base case alone: {fmt_idr(base_dcf_price)}." if base_dcf_price else "Discounted Cash Flow intrinsic valuation.",
            )
            st.markdown(
                f"""<div class="pillar-metrics">
                    <div class="p-row"><span>Base Case ({norm_probs.get('Base', 0.50):.0%})</span><b>{fmt_idr(base_dcf_price)}</b></div>
                    <div class="p-row"><span>Bear Case ({norm_probs.get('Bear', 0.25):.0%})</span><b>{fmt_idr(bear_price)}</b></div>
                    <div class="p-row"><span>Bull Case ({norm_probs.get('Bull', 0.25):.0%})</span><b>{fmt_idr(bull_price)}</b></div>
                    <div class="p-row"><span>WACC · Terminal g</span><b>{a.wacc*100:.2f}% · {a.terminal_growth*100:.2f}%</b></div>
                </div>""",
                unsafe_allow_html=True,
            )

        with p_col3:
            st.markdown(f'<div class="pillar-tag pillar-tag-rel"><span>PILLAR 3 · RELATIVE PEER CROSS-CHECK</span><span>{approach_eval["rel_weight"]:.0%} WEIGHT</span></div>', unsafe_allow_html=True)
            st.metric(
                "Relative value / share",
                fmt_idr(rel_price, default="Needs >= 2 peers") if (pd.notna(rel_price) and rel_price > 0) else "Needs >= 2 peers",
                help="Harmonic or median peer multiple cross-check across eligible IDX-IC sub-industry peer companies.",
            )
            st.markdown(
                f"""<div class="pillar-metrics">
                    <div class="p-row"><span>Lower Quartile (P25)</span><b>{q25_str}</b></div>
                    <div class="p-row"><span>Upper Quartile (P75)</span><b>{q75_str}</b></div>
                    <div class="p-row"><span>Gated Peers</span><b>{len(peer_rows)} peers matched</b></div>
                    <div class="p-row"><span>Multiples Applied</span><b>EV/EBITDA, EV/EBIT, P/E, P/BV</b></div>
                </div>""",
                unsafe_allow_html=True,
            )

    # 5. Valuation Charts Row (Equal 50:50 Desktop Split)
    ch_left, ch_right = st.columns([1, 1], gap="medium")
    with ch_left:
        st.markdown(
            '<div style="font-size:14px; font-weight:700; color:#1D1D1F; min-height:24px; margin-bottom:6px;">'
            'Valuation Range Comparison (Football Field)'
            '</div>',
            unsafe_allow_html=True,
        )
        ff_items = []
        base_price = result["price"] if result else None
        if bear_price and bull_price and base_price:
            ff_items.append({
                "Method": "DCF (FCFF) Range",
                "Low": min(bear_price, bull_price),
                "Mid": dcf_p if (dcf_p and pd.notna(dcf_p)) else base_price,
                "High": max(bear_price, bull_price),
                "Color": "#087F69",
            })
        if not relative.empty and len(peer_rows) >= 2:
            rel_med = rel_price if pd.notna(rel_price) else composite_relative_value(relative)
            if pd.notna(rel_med) and pd.notna(q25) and pd.notna(q75):
                ff_items.append({
                    "Method": "Relative (P25 - P75)",
                    "Low": min(q25, q75),
                    "Mid": rel_med,
                    "High": max(q25, q75),
                    "Color": "#2A6256",
                })
        if price and price > 0:
            ff_items.append({
                "Method": "Reference Price (±10%)",
                "Low": price * 0.90,
                "Mid": price,
                "High": price * 1.10,
                "Color": "#6E6E73",
            })

        if ff_items:
            fig_ff = go.Figure()
            for item in ff_items:
                fig_ff.add_trace(go.Bar(
                    name=item["Method"],
                    y=[item["Method"]],
                    x=[item["High"] - item["Low"]],
                    base=[item["Low"]],
                    orientation="h",
                    marker=dict(color=item["Color"], opacity=0.45, line=dict(color=item["Color"], width=1)),
                    hoverinfo="text",
                    hovertext=f"{item['Method']}: Rp {item['Low']:,.0f} – Rp {item['High']:,.0f} (Mid: Rp {item['Mid']:,.0f})",
                ))
                fig_ff.add_trace(go.Scatter(
                    x=[item["Mid"]],
                    y=[item["Method"]],
                    mode="markers+text",
                    marker=dict(color=item["Color"], size=10, symbol="diamond"),
                    text=[f"Rp {item['Mid']:,.0f}"],
                    textposition="top center",
                    textfont=dict(size=11, color="#1D1D1F"),
                    showlegend=False,
                ))
            if pd.notna(effective_price):
                fig_ff.add_vline(
                    x=effective_price, line_width=1.5, line_dash="dash", line_color="#087F69",
                    annotation_text=f"Blended: Rp {effective_price:,.0f}", annotation_position="top right",
                    annotation_font=dict(size=10.5, color="#087F69"),
                )
            fig_ff.update_layout(
                barmode="overlay", showlegend=False, height=310,
                template="plotly_white", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font=dict(family="-apple-system, BlinkMacSystemFont, 'SF Pro Text', sans-serif", color="#1D1D1F", size=11),
                margin=dict(l=145, r=20, t=30, b=30), xaxis_title="IDR / Share", yaxis=dict(autorange="reversed"),
            )
            fig_ff.update_xaxes(showgrid=True, gridcolor="#E5E5EA")
            fig_ff.update_yaxes(showgrid=False)
            st.plotly_chart(fig_ff, width="stretch", config=dict(displayModeBar=False))

    with ch_right:
        st.markdown(
            '<div style="font-size:14px; font-weight:700; color:#1D1D1F; min-height:24px; margin-bottom:6px;">'
            'Observed Market Price vs. Scenario Estimates'
            '</div>',
            unsafe_allow_html=True,
        )
        def _fmt_prob(p):
            pct = p * 100.0
            return f"{pct:.1f}%" if pct % 1 != 0 else f"{pct:.0f}%"

        scen_labels = ["Observed Market"] + [
            f"{x['Scenario']} ({_fmt_prob(norm_probs.get(x['Scenario'], x.get('Probability', 0.0)))})"
            for x in scenario_rows
        ]
        scen_vals = [price if (price and pd.notna(price)) else 0.0] + [
            (x["Value / share"] if (x.get("Value / share") is not None and pd.notna(x.get("Value / share"))) else 0.0)
            for x in scenario_rows
        ]
        scen_colors = ["#6E6E73", "#D97706", "#087F69", "#173E37"]
        max_sc_val = max(scen_vals) if scen_vals else 3000
        fig_sc_ov = go.Figure(go.Bar(
            x=scen_labels,
            y=scen_vals,
            marker_color=scen_colors[:len(scen_labels)],
            texttemplate="Rp %{y:,.0f}",
            textposition="outside",
            textfont=dict(size=11, color="#1D1D1F"),
            width=0.50,
        ))
        if price and price > 0:
            fig_sc_ov.add_hline(
                y=price, line_dash="dot", line_color="#8E8E93", line_width=1.5,
            )
        fig_sc_ov.update_layout(
            showlegend=False, height=310,
            template="plotly_white", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(family="-apple-system, BlinkMacSystemFont, 'SF Pro Text', sans-serif", color="#1D1D1F", size=11),
            margin=dict(l=40, r=20, t=30, b=30), yaxis_title="IDR / Share",
            yaxis=dict(range=[0, max_sc_val * 1.20]),
        )
        fig_sc_ov.update_xaxes(showgrid=False)
        fig_sc_ov.update_yaxes(gridcolor="#E5E5EA", zerolinecolor="#D1D1D6")
        st.plotly_chart(fig_sc_ov, width="stretch", config=dict(displayModeBar=False))

    # 6. Key Assumptions & Key Risks Adjacent Summary Cards (Level 3 — Drivers)
    ka_col, kr_col = st.columns(2)
    with ka_col:
        wacc_prov = "User Override" if a.wacc_override is not None else "CAPM + Synthetic Kd"
        st.markdown(
            f"""<div class="ov-card">
                <div>
                    <div class="ov-card-head">
                        <div class="ios-section-label">LEVEL 3 DRIVERS · KEY VALUATION ASSUMPTIONS</div>
                        <div class="ov-card-title">Core Operating &amp; Discount Drivers</div>
                    </div>
                    <table class="ov-assump-table">
                        <tbody>
                            <tr>
                                <td class="ov-label">Revenue Growth (Y1–3 &rarr; Y5)</td>
                                <td class="ov-val">{a.growth*100:.1f}% &rarr; {a.mature_growth*100:.1f}%</td>
                            </tr>
                            <tr>
                                <td class="ov-label">EBIT Margin (Y1–3 &rarr; Y5)</td>
                                <td class="ov-val">{a.ebit_margin*100:.1f}% &rarr; {a.mature_margin*100:.1f}%</td>
                            </tr>
                            <tr>
                                <td class="ov-label">CapEx &amp; Non-Cash NWC / Sales</td>
                                <td class="ov-val">{a.capex_pct*100:.1f}% &amp; {(a.nwc_pct or 0.0)*100:.1f}%</td>
                            </tr>
                            <tr>
                                <td class="ov-label">Effective WACC ({wacc_prov})</td>
                                <td class="ov-val">{a.wacc*100:.2f}% (Ke: {a.cost_of_equity*100:.2f}%)</td>
                            </tr>
                            <tr>
                                <td class="ov-label">Terminal Growth &amp; Terminal ROIC</td>
                                <td class="ov-val">{a.terminal_growth*100:.2f}% &amp; {a.terminal_roic*100:.1f}%</td>
                            </tr>
                            <tr>
                                <td class="ov-label">Approach Weights (DCF / Relative)</td>
                                <td class="ov-val">{approach_eval['dcf_weight']:.0%} / {approach_eval['rel_weight']:.0%}</td>
                            </tr>
                        </tbody>
                    </table>
                </div>
                <div class="ov-card-nav">
                    <span class="ov-nav-link" id="nav-btn-assumptions" role="button" tabindex="0">
                        View All Assumptions &rarr;
                    </span>
                </div>
            </div>""",
            unsafe_allow_html=True,
        )
    with kr_col:
        candidate_risks = []
        if is_dcf_ineligible:
            candidate_risks.append({
                "title": "Solvency Alert",
                "desc": f"Total debt (Rp {tot_debt:,.1f} bn) exceeds operating EV, resulting in negative intrinsic equity.",
                "badge_text": "CRITICAL",
                "badge_class": "ov-risk-badge-red",
            })
        if funding > 0.01:
            candidate_risks.append({
                "title": "Forecast Borrowing Need",
                "desc": f"5-year plan requires Rp {funding:,.1f} bn of cumulative new borrowing to sustain minimum cash buffer.",
                "badge_text": "WATCH",
                "badge_class": "ov-risk-badge-amber",
            })
        if term_share > 0.75:
            candidate_risks.append({
                "title": "Terminal Value Exposure",
                "desc": f"{term_share:.0%} of Enterprise Value rests on terminal perpetuity (>75% high sensitivity threshold).",
                "badge_text": "HIGH",
                "badge_class": "ov-risk-badge-amber",
            })
        else:
            candidate_risks.append({
                "title": "Terminal Value Exposure",
                "desc": f"{term_share:.0%} of Enterprise Value is derived from terminal perpetuity.",
                "badge_text": "NORMAL",
                "badge_class": "ov-risk-badge-gray",
            })
        if len(peer_rows) < 2:
            candidate_risks.append({
                "title": "Peer Sample Limitation",
                "desc": f"Only {len(peer_rows)} active peer(s) verified; Relative Valuation is gated off (100% DCF weight).",
                "badge_text": "LIMITED",
                "badge_class": "ov-risk-badge-amber",
            })
        if statement_age_days > 550:
            candidate_risks.append({
                "title": "Stale Reporting Period",
                "desc": f"Latest audited period ({period}) is {statement_age_days} days old (>18 months coverage threshold).",
                "badge_text": "STALE",
                "badge_class": "ov-risk-badge-amber",
            })
        candidate_risks.append({
            "title": "Historical Data Baseline",
            "desc": f"Forecast extrapolates from audited FY{period} figures without interim stub or post-FY{period} event adjustments.",
            "badge_text": "BASELINE",
            "badge_class": "ov-risk-badge-gray",
        })
        candidate_risks.append({
            "title": "Cost of Capital Sensitivity",
            "desc": f"Valuation is sensitive to Indo 10Y Rf ({a.risk_free*100:.2f}%), Beta ({a.beta:.2f}), and CRP ({a.country_risk_premium*100:.2f}%).",
            "badge_text": "MACRO",
            "badge_class": "ov-risk-badge-gray",
        })

        top_risks = candidate_risks[:3]
        risk_items_html = []
        for rk in top_risks:
            risk_items_html.append(
                f"""<div class="ov-risk-item">
                    <div class="ov-risk-header">
                        <span class="ov-risk-title">{rk['title']}</span>
                        <span class="ov-risk-badge {rk['badge_class']}">{rk['badge_text']}</span>
                    </div>
                    <p class="ov-risk-desc">{rk['desc']}</p>
                </div>"""
            )
        risk_html_content = "\n".join(risk_items_html)

        st.markdown(
            f"""<div class="ov-card">
                <div>
                    <div class="ov-card-head">
                        <div class="ios-section-label">LEVEL 3 &amp; 4 · KEY RISKS &amp; MODEL LIMITATIONS</div>
                        <div class="ov-card-title">Material Risks &amp; Active Model Boundaries</div>
                    </div>
                    <div class="ov-risk-list">
                        {risk_html_content}
                    </div>
                </div>
                <div class="ov-card-nav">
                    <span class="ov-nav-link" id="nav-btn-risks" role="button" tabindex="0">
                        View All Risks &amp; Audits &rarr;
                    </span>
                </div>
            </div>""",
            unsafe_allow_html=True,
        )

    # Client-side tab navigation handler for Overview Level 3 cards
    components.html(
        """
        <script>
            (function() {
                const parentDoc = window.parent.document;
                if (!parentDoc._overviewNavBound) {
                    parentDoc._overviewNavBound = true;
                    parentDoc.addEventListener('click', (e) => {
                        const assumpBtn = e.target.closest('#nav-btn-assumptions');
                        const riskBtn = e.target.closest('#nav-btn-risks');
                        if (assumpBtn || riskBtn) {
                            const tabs = Array.from(parentDoc.querySelectorAll('button[data-testid="stTab"], [role="tab"]'));
                            const labTab = tabs.find(t => t.innerText && t.innerText.includes("Valuation Lab"));
                            if (labTab) {
                                labTab.click();
                                setTimeout(() => {
                                    const subTabs = Array.from(parentDoc.querySelectorAll('button[data-testid="stTab"], [role="tab"]'));
                                    const targetName = assumpBtn ? "Valuation assumptions" : "Analyst review";
                                    const subTarget = subTabs.find(t => t.innerText && t.innerText.includes(targetName));
                                    if (subTarget) {
                                        subTarget.click();
                                    }
                                }, 80);
                            }
                        }
                    }, true);
                }
            })();
        </script>
        """,
        height=0,
        width=0,
    )

    # 7. Collapsible Evidence & Method Details (Level 5 — Detail on Demand)
    with st.expander("Valuation Approach Selection & Weight Justification (Rule 1 & Rule 2)", expanded=False):
        st.markdown(f"**Methodology Rationale**: {approach_eval['rationale']}")
        col_w1, col_w2, col_q = st.columns(3)
        col_w1.metric("DCF Weight (Intrinsic Anchor)", f"{approach_eval['dcf_weight']:.0%}")
        col_w2.metric("Relative Weight (Market Cross-Check)", f"{approach_eval['rel_weight']:.0%}")
        col_q.metric("Peer Group Quality", approach_eval["quality"])
        st.caption(
            "• **Rule 1 (Intrinsic Anchor)**: DCF (FCFF) is given primary emphasis (default 75%) because it measures intrinsic capacity to generate cash flows, independently of market sentiment or sector pricing bubbles.\n\n"
            "• **Rule 2 (Peer Quality Calibration)**: Relative valuation provides a secondary cross-check (25%) only when ≥2 sub-industry peers have verified financial similarity (EBITDA margin & DER); otherwise, model defaults to 100% DCF."
        )

    with st.expander("5-Year Revenue & Free Cash Flow Trajectory + Mathematical Formula Audit", expanded=False):
        l, r = st.columns([1.3, 1.0])
        with l:
            st.markdown("##### Historical & 5-Year Forecast Revenue vs. FCFF")
            fig = go.Figure()
            fig.add_scatter(x=[pd.Timestamp(x).year for x in historical.columns], y=historical.loc["revenue"], name="Reported revenue", line=dict(color="#6E6E73", width=3))
            fig.add_scatter(x=[first_year - 1] + list(f.index), y=[b["revenue"]] + list(f.revenue), name="Forecast revenue", line=dict(color="#087F69", width=3, dash="dash"))
            fig.add_bar(x=list(f.index), y=f.fcff, name="Free cash flow (FCFF)", marker_color="#B7E1D7")
            chart(fig)
        with r:
            st.markdown("##### Cost of Capital & Terminal Value Proof")
            total_erp = a.mature_equity_premium + a.country_risk_premium
            kd_after = a.debt_rate * (1 - a.tax_rate)
            we = 1 - a.debt_weight
            st.latex(rf"K_e = R_f + \beta \times \text{{Total ERP}} = {a.risk_free*100:.2f}\% + ({a.beta:.2f} \times {total_erp*100:.2f}\%) = {a.cost_of_equity*100:.2f}\%")
            st.latex(rf"\text{{WACC}} = (W_e \times K_e) + (W_d \times K_{{d,\text{{after}}}}) = {a.wacc*100:.2f}\%")
            if result:
                reinv_rate = result.get("terminal_reinvestment_rate", a.terminal_growth / a.terminal_roic)
                st.latex(rf"\text{{Terminal Value}} = \frac{{\text{{NOPAT}}_{{5}}(1+g)(1 - g/\text{{ROIC}})}}{{WACC - g}} = \text{{Rp }}{result['terminal_value']:,.1f}\text{{ bn}}")
                st.latex(rf"\text{{DCF / Share}} = \frac{{\text{{Equity Value}}}}{{\text{{Shares}}}} = \mathbf{{\text{{Rp }}{result['price']:,.0f}}}")

    if funding > .01:
        st.warning(f"The forecast requires IDR {funding:,.1f} bn of cumulative new borrowing. Review the funding schedule and sustainable leverage.")
    if not c["demo"] and statement_age_days > 550:
        st.warning("The latest common annual period is more than 18 months old. Review reporting coverage before relying on the result.")
    if has_neg_residual_bs:
        st.warning("A residual opening balance sheet bucket is negative. Review classification and source data.")

eff_w_dcf = float(approach_eval.get("dcf_weight", a.dcf_weight))
eff_w_rel = float(approach_eval.get("rel_weight", a.relative_weight))
tv_share = term_share
bear_p = bear_price
bull_p = bull_price
fv_low = fair_value_low
fv_high = fair_value_high
upside_pct = rec.get("upside") if isinstance(rec, dict) else None
rec_rating = rec.get("rating", "HOLD") if isinstance(rec, dict) else str(rec)
rec_pill_cls = "ios-pill-green" if rec_rating == "BUY" else ("ios-pill-red" if rec_rating in ("SELL", "NOT ELIGIBLE") else "ios-pill-amber")
prob_sum_check = sum(norm_probs.values()) if norm_probs else 1.0
validation_checks = [
    {
        "Check ID": "CHK-01",
        "Validation Rule": "Opening Balance Sheet Identity (Assets = Liabilities + Equity)",
        "Status": "PASS" if abs(bs_diff) <= 0.01 else "FAIL",
        "Measured Value": f"Diff: IDR {bs_diff:,.4f} bn",
        "Threshold / Standard": "|Diff| <= IDR 0.01 bn",
    },
    {
        "Check ID": "CHK-02",
        "Validation Rule": "5-Year Forecast Balance Sheet Reconciliation",
        "Status": "PASS" if fc_bs_max_diff <= 0.01 else "FAIL",
        "Measured Value": f"Max Diff: IDR {fc_bs_max_diff:,.6f} bn",
        "Threshold / Standard": "|Max Diff| <= IDR 0.01 bn across FY+1..FY+5",
    },
    {
        "Check ID": "CHK-03",
        "Validation Rule": "Reporting Currency & FX Normalization",
        "Status": "PASS" if c.get("financial_currency") == "IDR" else ("WARNING" if fx > 0 else "FAIL"),
        "Measured Value": f"{c.get('financial_currency', 'IDR')} (FX: {fx:,.1f})",
        "Threshold / Standard": "All statements & multiples normalized to IDR",
    },
    {
        "Check ID": "CHK-04",
        "Validation Rule": "Terminal Growth Discipline (g < WACC and g <= Nominal GDP)",
        "Status": "PASS" if (a.terminal_growth < a.wacc and a.terminal_growth <= 0.045) else ("FAIL" if a.terminal_growth >= a.wacc else "WARNING"),
        "Measured Value": f"g = {a.terminal_growth:.2%} vs. WACC = {a.wacc:.2%}",
        "Threshold / Standard": "g < WACC and g <= 4.50%",
    },
    {
        "Check ID": "CHK-05",
        "Validation Rule": "Terminal Value-Creation Spread (Terminal ROIC > Terminal g)",
        "Status": "PASS" if a.terminal_roic > a.terminal_growth else "WARNING",
        "Measured Value": f"ROIC = {a.terminal_roic:.2%} vs. g = {a.terminal_growth:.2%}",
        "Threshold / Standard": "ROIC > g (Reinvestment rate < 100%)",
    },
    {
        "Check ID": "CHK-06",
        "Validation Rule": "Comparable Peer Sample Breadth",
        "Status": "PASS" if len(peer_rows) >= 2 else "WARNING",
        "Measured Value": f"{len(peer_rows)} active peer(s)",
        "Threshold / Standard": ">= 2 valid peers required for Relative Valuation",
    },
    {
        "Check ID": "CHK-07",
        "Validation Rule": "Scenario Probability Normalization (Bear + Base + Bull)",
        "Status": "PASS" if abs(prob_sum_check - 1.0) <= 0.001 else "WARNING",
        "Measured Value": f"Total = {prob_sum_check:.1%}",
        "Threshold / Standard": "Normalized sum = 100.0%",
    },
    {
        "Check ID": "CHK-08",
        "Validation Rule": "Intrinsic Equity Solvency & Positive Value Check",
        "Status": "PASS" if not is_dcf_ineligible else "FAIL",
        "Measured Value": f"DCF = Rp {dcf_p:,.0f}/sh" if dcf_p is not None else "N/A",
        "Threshold / Standard": "Implied Equity Value > 0",
    },
    {
        "Check ID": "CHK-09",
        "Validation Rule": "Synchronized Intraday Historical Filing Date Quote",
        "Status": "NOT VERIFIED",
        "Measured Value": f"Filing FY {period} vs. current quote",
        "Threshold / Standard": "No stub-period roll-forward applied",
    },
]

with peers_tab:
    st.subheader("Comparable Peers & Relative Valuation")

    # ── TOP: SUMMARY ZONE ──
    rel_top_str = f"Rp {rel_price:,.0f}" if pd.notna(rel_price) else "N/A (< 2 valid peers)"
    rel_upside_top = ((rel_price / price - 1.0) if (pd.notna(rel_price) and price > 0) else None)
    rel_up_badge = f"{rel_upside_top:+.1%} vs. Market (Rp {price:,.0f})" if rel_upside_top is not None else "Requires ≥ 2 valid active peers"
    st.markdown(
        f"""
        <div class="ios-card" style="padding:14px 18px; margin-bottom:12px; display:flex; flex-wrap:wrap; justify-content:space-between; align-items:center; gap:12px;">
            <div>
                <div style="font-size:0.74rem; font-weight:700; text-transform:uppercase; letter-spacing:0.06em; color:#6E6E73;">Weighted Relative Valuation (Implied Price / Share)</div>
                <div style="font-size:1.55rem; font-weight:800; color:#1D1D1F; font-variant-numeric:tabular-nums;">{rel_top_str}</div>
            </div>
            <div style="text-align:right;">
                <span class="ios-pill {'ios-pill-teal' if pd.notna(rel_price) else 'ios-pill-amber'}">{rel_up_badge}</span>
                <div style="font-size:0.78rem; color:#6E6E73; margin-top:4px;">Aggregator: <b>{rel_agg_choice}</b> · Active Peers: <b>{len(peer_rows)}</b> · Blended Weight: <b>{eff_w_rel:.0%}</b></div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    card_cols = st.columns(4)
    metric_order = ["EV / EBITDA", "EV / EBIT", "P / E", "P / BV"]
    for idx, m_name in enumerate(metric_order):
        m_info = rel_breakdown.get(m_name, {})
        with card_cols[idx]:
            is_elig = m_info.get("eligible", False)
            price_val = m_info.get("implied_price")
            mult_val = m_info.get("peer_multiple")
            peers_used = m_info.get("peers_used", 0)
            eff_w = m_info.get("effective_weight", 0.0)

            excl_reasons = exclusion_info.get(m_name, []) if 'exclusion_info' in locals() else []
            if is_elig and pd.notna(price_val):
                p_display = fmt_idr(price_val)
                sub_display = f"{mult_val:.2f}x ({rel_agg_choice})" if (mult_val is not None and pd.notna(mult_val)) else f"— ({rel_agg_choice})"
                status_html = f"<span style='color: #087F69; font-weight: 700; font-size: 11px;'>ELIGIBLE ({peers_used} peers)</span>"
                note_html = ""
            else:
                p_display = "—"
                sub_display = f"{mult_val:.2f}x" if (mult_val is not None and pd.notna(mult_val)) else "No peers"
                status_html = f"<span style='color: #B25000; font-weight: 700; font-size: 11px;'>INELIGIBLE ({peers_used}/2 peers)</span>"
                note_html = f"<div style='font-size: 10px; color: #8a5314; margin-top: 4px; line-height: 1.25;'>Excluded {', '.join(excl_reasons)} to prevent negative multiple distortion.</div>" if excl_reasons else ""

            card_html = (
                f'<div class="ios-card" style="padding: 14px; margin-bottom: 8px;">'
                f'<div style="font-size: 11px; text-transform: uppercase; color: #6E6E73; font-weight: 700;">{m_name}</div>'
                f'<div style="font-size: 22px; font-weight: 800; color: #1D1D1F; margin: 4px 0; font-variant-numeric: tabular-nums;">{p_display}</div>'
                f'<div style="font-size: 12px; color: #6E6E73;">{sub_display} &nbsp;|&nbsp; Eff. W: <b>{eff_w:.0%}</b></div>'
                f'<div style="margin-top: 4px;">{status_html}</div>'
                f'{note_html}'
                f'</div>'
            )
            st.markdown(card_html, unsafe_allow_html=True)

    st.divider()

    # ── MIDDLE: SELECTION ZONE ──
    st.markdown('<div class="ios-sub-header" style="margin-top:4px;">Selection · Peer Universe, Similarity Ranking & Rationale</div>', unsafe_allow_html=True)
    c_input, c_btn1, c_btn2 = st.columns([3, 1, 1])
    with c_input:
        manual_peer_text = st.text_input(
            "Manual Additional Peers",
            value="",
            placeholder="e.g. UNVR, ICBP, INDF",
            key=key("manual_peer_input"),
            help="Enter additional IDX tickers separated by commas to add them to the peer comparison set. Target is excluded."
        )
    with c_btn1:
        st.write("")
        st.write("")
        if st.button("Add Peers", type="primary", key=key("fetch_peers"), width="stretch"):
            raw_symbols = [v.strip().upper().replace(".JK", "") for v in manual_peer_text.split(",") if v.strip()]
            clean_target = c["symbol"].replace(".JK", "").upper()
            existing_symbols = {pc["symbol"].replace(".JK", "").upper() for pc in st.session_state.get("peer_companies", [])}

            new_symbols = []
            new_errs = list(st.session_state.get("peer_errors", []))
            for sym in raw_symbols:
                if sym == clean_target:
                    new_errs.append(f"{sym}: Target company cannot be added as its own peer.")
                elif sym in existing_symbols:
                    st.session_state[key(f"include_{sym}.JK")] = True
                    st.session_state[key(f"include_{sym}")] = True
                else:
                    new_symbols.append(sym)

            if new_symbols:
                with st.spinner("Fetching peer statements via DoH…"):
                    new_pcs, fetch_errs = get_or_fetch_peers(new_symbols, target_symbol=c["symbol"])
                    st.session_state.peer_companies = list(st.session_state.get("peer_companies", [])) + new_pcs
                    for pc in new_pcs:
                        st.session_state[key(f"include_{pc['symbol']}")] = True
                    new_errs.extend(fetch_errs)
            st.session_state.peer_errors = new_errs
            st.rerun()
    with c_btn2:
        st.write("")
        st.write("")
        if st.button("Reset Defaults", key=key("reset_peers"), width="stretch"):
            suggested = get_default_peers_for_ticker(c["symbol"], c.get("industry"))
            with st.spinner("Loading default peers…"):
                new_pcs, new_errs = get_or_fetch_peers(suggested[:4], target_symbol=c["symbol"])
                st.session_state.peer_companies = new_pcs
                st.session_state.peer_errors = new_errs
                for pc in new_pcs:
                    st.session_state[key(f"include_{pc['symbol']}")] = True
            st.rerun()

    for err in st.session_state.get("peer_errors", []):
        st.warning(err)

    all_pcs = st.session_state.get("peer_companies", [])
    if all_pcs:
        st.caption("Peers are ranked by financial similarity (EBITDA Margin & Debt-to-Equity DER distance). Use checkboxes to include or exclude individual peers from valuation.")

        all_candidate_rows = []
        for pc in all_pcs:
            try:
                p_fx = fx if pc.get("financial_currency") == "USD" else 1.0
                p_cand = peer_record(pc, period, fx=p_fx)
                all_candidate_rows.append(p_cand)
            except Exception:
                pass

        ranked_all = rank_peers_similarity(target_profile, all_candidate_rows) if all_candidate_rows else []
        rank_map = {r["ticker"]: r for r in ranked_all}

        table_rows = []
        target_sub_ind = c.get("industry") or (get_company_idx_metadata(c["symbol"]) or {}).get("sub_industry", "—")
        table_rows.append({
            "Active": "TARGET",
            "Ticker": c["symbol"],
            "Company Name": clean_company_name(c["name"]),
            "Sub-Industry": target_sub_ind,
            "EBITDA Margin": f"{target_profile['ebitda_margin']:.1%}",
            "DER (D/E)": f"{target_profile['der']:.2f}x",
            "Similarity & Confidence": "100/100 (Benchmark)",
        })

        sorted_pcs = sorted(
            all_pcs,
            key=lambda p: rank_map.get(p["symbol"], {}).get("similarity_distance", 999.0)
        )

        cols_cb = st.columns(min(4, max(1, len(sorted_pcs))))
        for idx, pc in enumerate(sorted_pcs):
            sym = pc["symbol"]
            clean_sym = sym.replace('.JK', '')
            with cols_cb[idx % len(cols_cb)]:
                is_inc = st.checkbox(f"Include {clean_sym}", value=st.session_state.get(key(f"include_{sym}"), True), key=key(f"include_{sym}"))

            r_info = rank_map.get(sym, {})
            m_val = r_info.get("ebitda_margin")
            der_val = r_info.get("der")
            score_val = r_info.get("similarity_score", 100)
            conf_val = r_info.get("confidence_level", "High")
            p_sub_ind = pc.get("industry") or (get_company_idx_metadata(sym) or {}).get("sub_industry", "—")

            table_rows.append({
                "Active": "INCLUDED" if is_inc else "EXCLUDED",
                "Ticker": sym,
                "Company Name": clean_company_name(pc["name"]),
                "Sub-Industry": p_sub_ind,
                "EBITDA Margin": f"{m_val:.1%}" if m_val is not None else "—",
                "DER (D/E)": f"{der_val:.2f}x" if der_val is not None else "—",
                "Similarity & Confidence": f"{score_val}/100 ({conf_val} Confidence)",
            })

        st.markdown(
            render_apple_table(
                pd.DataFrame(table_rows),
                title="Comparable Peers Screening & Financial Comparability",
                unit_label=f"Target: {c.get('symbol', 'Target')} · Benchmark Distance Ranking",
                hide_index=True,
                highlight_rows=[c["symbol"]],
                col_alignments={
                    "Active": "col-center",
                    "Ticker": "col-center",
                    "Company Name": "col-text",
                    "Sub-Industry": "col-text",
                    "EBITDA Margin": "col-num",
                    "DER (D/E)": "col-num",
                    "Similarity & Confidence": "col-num",
                },
                badge_cols={
                    "Active": {"TARGET": "pass", "INCLUDED": "pass", "EXCLUDED": "info"},
                },
            ),
            unsafe_allow_html=True,
        )
        st.caption("Similarity score (0–100) measures financial comparability based on EBITDA margin and DER leverage alignment relative to target. Confidence tiers: ≥75 High Confidence (strong match), 50–74 Moderate Confidence, <50 Low Confidence.")

        with st.expander("Why Selected? · Peer Selection & Similarity Rationale", expanded=False):
            for r_peer in ranked_all:
                st.markdown(f"- **{r_peer.get('ticker', '')} ({clean_company_name(r_peer.get('name', ''))})**: {explain_peer_selection(target_profile, r_peer)}")
    else:
        st.info("No peers currently loaded. Click 'Reset Defaults' above to automatically load suggested peers.")

    # ── BOTTOM: METHOD ZONE ──
    st.divider()
    st.markdown('<div class="ios-sub-header" style="margin-top:4px;">Method · Aggregator, Multiple Weights & Distribution</div>', unsafe_allow_html=True)

    if len(peer_rows) < 2:
        st.warning(f"Policy Rule Active: Minimum 2 valid active peers required for relative multiples (currently {len(peer_rows)} active). DCF has 100% weighting.")
    else:
        st.success(f"Peer criteria met: {len(peer_rows)} active comparable peers.")

    c_agg, c_w1, c_w2, c_w3, c_w4 = st.columns([1.5, 1, 1, 1, 1])
    with c_agg:
        sel_agg = st.selectbox(
            "Benchmark Multiple Aggregator",
            ["Median", "Harmonic mean"],
            index=0 if rel_agg_choice == "Median" else 1,
            key=key("rel_agg_choice"),
            help="Median is the market standard. Harmonic Mean eliminates upward skew from near-zero earnings (Damodaran & Bhojraj-Lee)."
        )
    with c_w1:
        st.number_input("EV / EBITDA Weight (%)", min_value=0.0, max_value=100.0, value=w_ebitda, step=5.0, key=key("w_mult_ebitda"))
    with c_w2:
        st.number_input("EV / EBIT Weight (%)", min_value=0.0, max_value=100.0, value=w_ebit, step=5.0, key=key("w_mult_ebit"))
    with c_w3:
        st.number_input("P / E Weight (%)", min_value=0.0, max_value=100.0, value=w_pe, step=5.0, key=key("w_mult_pe"))
    with c_w4:
        st.number_input("P / BV Weight (%)", min_value=0.0, max_value=100.0, value=w_pbv, step=5.0, key=key("w_mult_pbv"))

    if abs(tot_mult_w - 100.0) > 0.01:
        st.warning(f"Multiple weights sum to {tot_mult_w:.1f}%. Calculation automatically normalizes weights to 100%.")
    else:
        st.caption("Weights validated: 100.0% total allocation.")

    if not relative.empty:
        filtered_relative = relative[relative["Case"] == sel_agg] if "Case" in relative.columns else relative
        if "Peers used" in filtered_relative.columns:
            filtered_relative = filtered_relative[
                (filtered_relative["Peers used"] >= 2) &
                (filtered_relative["Implied price (IDR)"].notna()) &
                (filtered_relative["Implied price (IDR)"] > 0)
            ].copy()

        any_discarded = any(not info.get("eligible", False) for info in rel_breakdown.values()) if rel_breakdown else False
        weight_col_name = "Normalized weight" if any_discarded else "Weight"

        if not filtered_relative.empty and rel_breakdown:
            filtered_relative[weight_col_name] = filtered_relative["Multiple"].map(
                lambda m: rel_breakdown.get(m, {}).get("effective_weight", 0.0) * 100.0
            )
            col_order = ["Multiple", "Case", "Eligible peers", "Peer multiple", weight_col_name, "Implied price (IDR)"]
            filtered_relative = filtered_relative[[c_col for c_col in col_order if c_col in filtered_relative.columns]]

        st.markdown(f"**Multiples Benchmark & Implied Value ({sel_agg})**")
        if not filtered_relative.empty:
            st.markdown(
                render_apple_table(
                    filtered_relative,
                    title=f"Multiples Benchmark & Implied Value ({sel_agg})",
                    unit_label="Relative Valuation Matrix · Comparable Multiples",
                    hide_index=True,
                    col_formats={
                        "Peer multiple": "{:,.2f}x",
                        weight_col_name: "{:.1f}%",
                        "Implied price (IDR)": "Rp {:,.0f}",
                    },
                    col_alignments={
                        "Multiple": "col-text",
                        "Case": "col-center",
                        "Eligible peers": "col-text",
                        "Peer multiple": "col-num",
                        weight_col_name: "col-num",
                        "Implied price (IDR)": "col-num",
                    },
                    highlight_rows=["EV / EBITDA", "P / E"],
                ),
                unsafe_allow_html=True,
            )
        else:
            st.info("No multiples meet the eligibility requirement (minimum 2 valid peers required). DCF approach has 100% weighting.")

        st.markdown("##### Implied Price per Share Comparison")
        chart_bars = []
        bar_colors = []
        bar_labels = []

        if pd.notna(rel_price):
            chart_bars.append(rel_price)
            bar_labels.append("Weighted Relative")
            bar_colors.append("#087F69")

        if dcf_p and pd.notna(dcf_p):
            chart_bars.append(dcf_p)
            bar_labels.append("DCF Fair Value")
            bar_colors.append("#0066CC")

        if price and pd.notna(price):
            chart_bars.append(price)
            bar_labels.append("Observed Market Price")
            bar_colors.append("#6E6E73")

        fig_rv = go.Figure(go.Bar(
            x=bar_labels,
            y=chart_bars,
            marker_color=bar_colors,
            text=[fmt_idr(v) for v in chart_bars],
            textposition="auto"
        ))
        chart(fig_rv, "IDR / share")

with analyst_review_tab:
    st.subheader("Key Assumptions, Investment Risks & Model Review")
    st.caption(
        "Audit core valuation assumptions, categorized risk exposures, model boundaries, and automated integrity checks "
        "before interpreting final fair-value targets."
    )

    # ── PANEL A: KEY ASSUMPTIONS ──
    st.markdown('<div class="ios-sub-header" style="margin-top:4px;">Panel A · Key Assumptions & Provenance Audit</div>', unsafe_allow_html=True)
    inf_a = inferred_assumptions()
    assump_audit_rows = [
        {
            "Category": "Operating & Growth",
            "Parameter": "Revenue Growth (Years 1–3)",
            "Effective Value": f"{a.growth:.2%}",
            "Inferred Default": f"{inf_a.growth:.2%}",
            "Provenance": "User Override" if abs(a.growth - inf_a.growth) > 1e-4 else "Model Inferred",
            "Economic Rationale": "Near-term top-line expansion rate during explicit forecast years 1–3.",
        },
        {
            "Category": "Operating & Growth",
            "Parameter": "Mature Revenue Growth (Years 4–5)",
            "Effective Value": f"{a.mature_growth:.2%}",
            "Inferred Default": f"{inf_a.mature_growth:.2%}",
            "Provenance": "User Override" if abs(a.mature_growth - inf_a.mature_growth) > 1e-4 else "Model Inferred",
            "Economic Rationale": "Linear transition rate tapering toward steady-state perpetuity growth.",
        },
        {
            "Category": "Operating & Profitability",
            "Parameter": "EBIT Margin (Years 1–3)",
            "Effective Value": f"{a.ebit_margin:.2%}",
            "Inferred Default": f"{inf_a.ebit_margin:.2%}",
            "Provenance": "User Override" if abs(a.ebit_margin - inf_a.ebit_margin) > 1e-4 else "Model Inferred",
            "Economic Rationale": "Operating profitability before interest and taxes (1 − COGS% − OpEx% − D&A%).",
        },
        {
            "Category": "Operating & Profitability",
            "Parameter": "Mature EBIT Margin (Year 5)",
            "Effective Value": f"{a.mature_margin:.2%}",
            "Inferred Default": f"{inf_a.mature_margin:.2%}",
            "Provenance": "User Override" if abs(a.mature_margin - inf_a.mature_margin) > 1e-4 else "Model Inferred",
            "Economic Rationale": "Normalized sustainable operating margin entering terminal period.",
        },
        {
            "Category": "Reinvestment & Capital",
            "Parameter": "CapEx (% of Revenue)",
            "Effective Value": f"{a.capex_pct:.2%}",
            "Inferred Default": f"{inf_a.capex_pct:.2%}",
            "Provenance": "User Override" if abs(a.capex_pct - inf_a.capex_pct) > 1e-4 else "Model Inferred",
            "Economic Rationale": "Capital intensity required to sustain physical asset base and capacity growth.",
        },
        {
            "Category": "Cost of Capital (WACC)",
            "Parameter": "Calculated WACC",
            "Effective Value": f"{a.wacc:.2%}",
            "Inferred Default": f"{inf_a.wacc:.2%}",
            "Provenance": "User Override" if (a.wacc_override is not None or abs(a.wacc - inf_a.wacc) > 1e-4) else "Model Inferred (CAPM + CRP)",
            "Economic Rationale": f"Ke = {a.cost_of_equity:.2%} (Rf {a.risk_free:.2%}, Beta {a.beta:.2f}, ERP {a.mature_equity_premium:.2%}, CRP {a.country_risk_premium:.2%}); Post-tax Kd = {a.debt_rate * (1 - a.tax_rate):.2%}.",
        },
        {
            "Category": "Terminal Economics",
            "Parameter": "Terminal Growth Rate (g)",
            "Effective Value": f"{a.terminal_growth:.2%}",
            "Inferred Default": f"{inf_a.terminal_growth:.2%}",
            "Provenance": "User Override" if abs(a.terminal_growth - inf_a.terminal_growth) > 1e-4 else "Model Inferred",
            "Economic Rationale": "Perpetual growth rate beyond Year 5; must remain below WACC and nominal GDP.",
        },
        {
            "Category": "Terminal Economics",
            "Parameter": "Terminal Return on Invested Capital (ROIC)",
            "Effective Value": f"{a.terminal_roic:.2%}",
            "Inferred Default": f"{inf_a.terminal_roic:.2%}",
            "Provenance": "User Override" if abs(a.terminal_roic - inf_a.terminal_roic) > 1e-4 else "Model Inferred",
            "Economic Rationale": f"Determines perpetual reinvestment rate (g / ROIC = {(a.terminal_growth / a.terminal_roic):.1%}).",
        },
        {
            "Category": "Valuation Policy",
            "Parameter": "Blended Method Weights (DCF / Relative)",
            "Effective Value": f"{eff_w_dcf:.0%} DCF / {eff_w_rel:.0%} Relative",
            "Inferred Default": f"{inf_a.dcf_weight:.0%} DCF / {inf_a.relative_weight:.0%} Relative",
            "Provenance": "User Override" if (abs(a.dcf_weight - inf_a.dcf_weight) > 1e-4 or abs(a.relative_weight - inf_a.relative_weight) > 1e-4) else "Policy Default",
            "Economic Rationale": "Triangulates intrinsic cash-flow value with observable market peer pricing.",
        },
    ]
    st.markdown(
        render_apple_table(
            pd.DataFrame(assump_audit_rows),
            title="Comprehensive Valuation Assumptions Audit & Provenance Log",
            unit_label="Economic Drivers & Method Calibration",
            hide_index=True,
            col_alignments={
                "Category": "col-text",
                "Parameter": "col-text",
                "Effective Value": "col-num",
                "Inferred Default": "col-num",
                "Provenance": "col-center",
                "Economic Rationale": "col-text",
            },
            badge_cols={
                "Provenance": {"User Override": "warn", "Model Inferred": "info", "Policy Default": "info"},
            },
        ),
        unsafe_allow_html=True,
    )

    # ── PANEL B: KEY RISKS ──
    st.markdown('<div class="ios-sub-header">Panel B · Categorized Investment & Valuation Risks</div>', unsafe_allow_html=True)
    st.caption("Distinguishes between system-detected model facts, general analytical considerations, and analyst-entered thesis notes.")
    rk_col1, rk_col2 = st.columns(2, gap="medium")
    with rk_col1:
        st.markdown(
            f"""
            <div class="ios-card" style="padding:16px;">
                <div style="font-size:0.76rem; font-weight:700; text-transform:uppercase; color:#B25000; margin-bottom:8px;">System-Detected Model & Financial Risk Facts</div>
                <ul style="margin:0; padding-left:18px; font-size:0.84rem; color:#1D1D1F; line-height:1.6;">
                    <li><b>Valuation / Forecasting Risk (Terminal Concentration)</b>: Terminal value represents <b>{tv_share:.1%}</b> of total DCF Enterprise Value ({'HIGH sensitivity (>75%)' if tv_share > 0.75 else 'within normal bounds (≤75%)'}).</li>
                    <li><b>Financial / Capital-Structure Risk (Liquidity & Debt)</b>: Opening Debt/Equity is <b>{target_profile['der']:.2f}x</b>; cumulative 5-year revolver borrowing need is <b>IDR {funding:,.1f} bn</b>.</li>
                    <li><b>Valuation / Forecasting Risk (Peer Sample Breadth)</b>: Active comparable peer count is <b>{len(peer_rows)}</b> ({'below 2-peer policy minimum — Relative Valuation disabled' if len(peer_rows) < 2 else 'meets ≥2 peer policy requirement'}).</li>
                    <li><b>Data-Quality Risk (Statement Recency)</b>: Base fiscal period is <b>{period}</b> ({f'{statement_age_days} days old — STALE (>18 months)' if (not c['demo'] and statement_age_days > 550) else 'current annual filing'}).</li>
                    <li><b>Baseline Period Anchor (FY2025 Model Horizon)</b>: Projections anchor strictly on audited FY{period} statements; unreflected interim operating developments post-FY2025 are not incorporated in baseline inputs.</li>
                </ul>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with rk_col2:
        st.markdown(
            f"""
            <div class="ios-card" style="padding:16px;">
                <div style="font-size:0.76rem; font-weight:700; text-transform:uppercase; color:#0066CC; margin-bottom:8px;">General Analytical Considerations (6 Risk Domains)</div>
                <ul style="margin:0; padding-left:18px; font-size:0.84rem; color:#1D1D1F; line-height:1.6;">
                    <li><b>1. Business / Operating Risk</b>: Margin compression if input inflation or competitive pricing prevents achieving the {a.mature_margin:.1%} Year-5 EBIT margin target.</li>
                    <li><b>2. Financial / Capital-Structure Risk</b>: Refinancing exposure if debt rollover occurs at higher corporate credit spreads than {a.debt_rate:.2%}.</li>
                    <li><b>3. Market / Macro Risk</b>: Sensitivity to 10Y IndoGB sovereign yields ({a.risk_free:.2%}), Country Risk Premium ({a.country_risk_premium:.2%}), and USD/IDR exchange rate fluctuations.</li>
                    <li><b>4. Valuation / Forecasting Risk</b>: Execution variance across the 5-year explicit horizon and peer multiple compression.</li>
                    <li><b>5. Data-Quality Risk</b>: Automated Yahoo Finance taxonomy mapping of PSAK accounts and non-operating items.</li>
                    <li><b>6. Baseline Period &amp; Interim Risk (FY2025 Anchor)</b>: Explicit 5-year projections extrapolate from audited FY2025 figures without rolling interim stub adjustments.</li>
                </ul>
            </div>
            """,
            unsafe_allow_html=True,
        )

    analyst_custom_risk_notes = ""

    # ── PANEL C: MODEL LIMITATIONS ──
    st.markdown('<div class="ios-sub-header">Panel C · Verified Model Boundaries & Structural Limitations</div>', unsafe_allow_html=True)
    st.markdown(
        f"""
        <div class="ios-card" style="padding:16px;">
            <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap:12px; font-size:0.84rem; color:#1D1D1F; line-height:1.55;">
                <div><b>1. Explicit Horizon & Constant WACC</b><br><span style="color:#6E6E73;">Uses a 5-year explicit annual forecast followed by a Year-6 Gordon Growth perpetuity with a single constant WACC ({a.wacc:.2%}) across all periods.</span></div>
                <div><b>2. Year-End Discounting (No Stub Adjustment)</b><br><span style="color:#6E6E73;">Cash flows are discounted at full fiscal-year intervals from {period} and compared against the current market price without intra-year stub roll-forward.</span></div>
                <div><b>3. Simplified Liquidity Revolver & Taxes</b><br><span style="color:#6E6E73;">Cash shortfalls automatically draw short-term debt to maintain a 2% revenue cash buffer; interest uses opening debt (no circularity) and taxes exclude NOL carryforwards.</span></div>
                <div><b>4. Operating Company Scope & Data Feed</b><br><span style="color:#6E6E73;">Designed for non-financial operating companies. Relies on standardized Yahoo Finance (`yfinance`) annual statements without segment-level or M&A modeling.</span></div>
                <div><b>5. FY2025 Baseline Period Anchor</b><br><span style="color:#6E6E73;">All 5-year forecast trajectories project forward from the FY2025 base fiscal period ({period}) without intra-year stub rolling or forward guidance adjustments.</span></div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── PANEL D: MODEL VALIDATION ──
    st.markdown('<div class="ios-sub-header">Panel D · Executed Model Validation & Integrity Checks</div>', unsafe_allow_html=True)
    st.markdown(
        render_apple_table(
            pd.DataFrame(validation_checks),
            title="Automated Model Integrity & Validation Checks",
            unit_label="Rigorous Pre-Flight Audit",
            hide_index=True,
            col_alignments={
                "Check ID": "col-center",
                "Validation Rule": "col-text",
                "Status": "col-center",
                "Measured Value": "col-num",
                "Threshold / Standard": "col-text",
            },
            badge_cols={
                "Status": {"PASS": "pass", "FAIL": "fail", "WARNING": "warn", "NOT VERIFIED": "info"},
            },
        ),
        unsafe_allow_html=True,
    )

with dcf_tab:
    st.subheader("DCF & Relative Valuation")
    st.caption(
        "Executive summary of intrinsic cash-flow valuation, enterprise-to-equity valuation schedule, "
        "and terminal perpetuity discipline, followed by expandable 5-year connected financial statements and mathematical proofs."
    )
    if result:
        # ── 1. SYMMETRICAL 4-COLUMN KPI SUMMARY STRIP ──
        dcf_fair_val_str = f"Rp {result['price']:,.0f}" if pd.notna(result.get("price")) else "N/A"
        dcf_sub_str = (
            f"Expected (Scenario-Weighted): Rp {expected_dcf_price:,.0f}"
            if (expected_dcf_price is not None and pd.notna(expected_dcf_price))
            else f"Base DCF · Weight: {eff_w_dcf:.0%}"
        )
        ev_val_str = f"IDR {result['enterprise_value']:,.1f} bn"
        ev_sub_str = f"PV of explicit FCFF: IDR {result['pv_flows']:,.1f} bn"
        eq_val_str = f"IDR {result['equity_value']:,.1f} bn"
        eq_sub_str = f"Terminal Value share: {result['terminal_share']:.1%} of EV"
        rel_val_str = f"Rp {rel_price:,.0f}" if pd.notna(rel_price) else "N/A"
        rel_sub_str = f"{len(peer_rows)} active peers ({rel_agg_choice} · {eff_w_rel:.0%} weight)"

        st.markdown(
            f"""
            <div class="dcf-kpi-grid">
                <div class="dcf-kpi-card dcf-kpi-card-highlight">
                    <div class="dcf-kpi-label">DCF Fair Value / Share</div>
                    <div class="dcf-kpi-value dcf-kpi-value-accent">{dcf_fair_val_str}</div>
                    <div class="dcf-kpi-sub">{dcf_sub_str}</div>
                </div>
                <div class="dcf-kpi-card">
                    <div class="dcf-kpi-label">Enterprise Value (EV)</div>
                    <div class="dcf-kpi-value">{ev_val_str}</div>
                    <div class="dcf-kpi-sub">{ev_sub_str}</div>
                </div>
                <div class="dcf-kpi-card">
                    <div class="dcf-kpi-label">Implied Equity Value</div>
                    <div class="dcf-kpi-value">{eq_val_str}</div>
                    <div class="dcf-kpi-sub">{eq_sub_str}</div>
                </div>
                <div class="dcf-kpi-card">
                    <div class="dcf-kpi-label">Relative Value / Share</div>
                    <div class="dcf-kpi-value">{rel_val_str}</div>
                    <div class="dcf-kpi-sub">{rel_sub_str}</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # ── 2 & 3. 50:50 SYMMETRICAL LAYOUT: EQUITY BRIDGE vs. TERMINAL ECONOMICS ──
        col1, col2 = st.columns([1, 1], gap="medium")

        with col1:
            st.markdown(
                '<div class="dcf-panel-heading">'
                '<span>Enterprise-to-Equity Value Bridge</span>'
                '<span class="dcf-panel-unit">Unit: IDR billion (except per share)</span>'
                '</div>',
                unsafe_allow_html=True,
            )
            pv_flows_v = float(result["pv_flows"])
            pv_term_v = float(result["pv_terminal"])
            ev_v = float(result["enterprise_value"])
            cash_v = float(b["cash"])
            nonop_v = float(a.nonoperating_assets)
            debt_v = -float(b["short_debt"] + b["long_debt"])
            claims_v = -float(a.other_claims)
            eq_v = float(result["equity_value"])
            dcf_ps_v = float(result["price"])

            pv_flows_pct = (pv_flows_v / ev_v * 100.0) if ev_v else 0.0
            pv_term_pct = (pv_term_v / ev_v * 100.0) if ev_v else 0.0

            def _fmt_sched_amt(val, signed=False):
                if val < 0:
                    return f"({abs(val):,.1f})"
                if signed and val > 0:
                    return f"+{val:,.1f}"
                return f"{val:,.1f}"

            st.markdown(
                f"""
                <div class="dcf-panel-card">
                    <table class="fin-schedule-table">
                        <thead>
                            <tr>
                                <th>Valuation Component</th>
                                <th class="num">Basis / Share</th>
                                <th class="num">Amount (IDR bn)</th>
                            </tr>
                        </thead>
                        <tbody>
                            <tr class="sec-group"><td colspan="3">A. Enterprise Valuation</td></tr>
                            <tr class="item-row">
                                <td>PV of Explicit Forecast FCFF (Years 1–5)</td>
                                <td class="num" style="color:#6E6E73;">{pv_flows_pct:.1f}% of EV</td>
                                <td class="num">{_fmt_sched_amt(pv_flows_v)}</td>
                            </tr>
                            <tr class="item-row">
                                <td>PV of Terminal Value (Year 6+ Perpetuity)</td>
                                <td class="num" style="color:#6E6E73;">{pv_term_pct:.1f}% of EV</td>
                                <td class="num">{_fmt_sched_amt(pv_term_v)}</td>
                            </tr>
                            <tr class="subtotal-row">
                                <td>Enterprise Value (EV)</td>
                                <td class="num">100.0% of EV</td>
                                <td class="num">{_fmt_sched_amt(ev_v)}</td>
                            </tr>
                            <tr class="sec-group"><td colspan="3">B. Enterprise-to-Equity Adjustments</td></tr>
                            <tr class="item-row">
                                <td>Add: Opening Cash &amp; Marketable Securities</td>
                                <td class="num" style="color:#6E6E73;">+Rp {(cash_v / shares):,.0f}/sh</td>
                                <td class="num">{_fmt_sched_amt(cash_v, signed=True)}</td>
                            </tr>
                            <tr class="item-row">
                                <td>Add: Non-Operating Assets</td>
                                <td class="num" style="color:#6E6E73;">+Rp {(nonop_v / shares):,.0f}/sh</td>
                                <td class="num">{_fmt_sched_amt(nonop_v, signed=True)}</td>
                            </tr>
                            <tr class="item-row">
                                <td>Less: Opening Total Financial Debt (ST + LT)</td>
                                <td class="num" style="color:#6E6E73;">−Rp {(abs(debt_v) / shares):,.0f}/sh</td>
                                <td class="num">{_fmt_sched_amt(debt_v)}</td>
                            </tr>
                            <tr class="item-row">
                                <td>Less: Minority Interest &amp; Other Claims</td>
                                <td class="num" style="color:#6E6E73;">−Rp {(abs(claims_v) / shares):,.0f}/sh</td>
                                <td class="num">{_fmt_sched_amt(claims_v)}</td>
                            </tr>
                            <tr class="sec-group"><td colspan="3">C. Final Equity Valuation</td></tr>
                            <tr class="subtotal-row">
                                <td>Implied Intrinsic Equity Value</td>
                                <td class="num">Common Equity</td>
                                <td class="num">{_fmt_sched_amt(eq_v)}</td>
                            </tr>
                            <tr class="item-row">
                                <td>Diluted Shares Outstanding</td>
                                <td class="num" style="color:#6E6E73;">Billion shares</td>
                                <td class="num">{shares:,.3f} bn</td>
                            </tr>
                            <tr class="final-row">
                                <td>DCF Fair Value per Share (Base Case)</td>
                                <td class="num">{f"Expected: Rp {expected_dcf_price:,.0f}" if (expected_dcf_price and pd.notna(expected_dcf_price)) else "Intrinsic Base"}</td>
                                <td class="num">Rp {dcf_ps_v:,.0f}</td>
                            </tr>
                        </tbody>
                    </table>
                    <div class="dcf-footnote">
                        Note: Parentheses indicate negative bridge deductions. Enterprise-to-equity adjustments use audited opening balance sheet balances (FY {period}) to avoid double-counting explicit forecast cash flows.
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with col2:
            st.markdown(
                '<div class="dcf-panel-heading">'
                '<span>Terminal Economics &amp; Perpetuity Discipline</span>'
                '<span class="dcf-panel-unit">Damodaran Value-Driver Model (Year 6+)</span>'
                '</div>',
                unsafe_allow_html=True,
            )
            reinv_rate = float(result.get("terminal_reinvestment_rate", a.terminal_growth / a.terminal_roic))
            term_nopat_v = float(result["terminal_nopat"])
            term_fcff_v = float(result["terminal_fcff"])
            term_reinv_amt = term_nopat_v - term_fcff_v
            term_val_v = float(result["terminal_value"])
            pv_term_v = float(result["pv_terminal"])
            tv_share_pct = float(result["terminal_share"]) * 100.0
            fcff_share_pct = max(0.0, 100.0 - tv_share_pct)
            exit_mult_v = result.get("implied_exit_ev_ebitda")
            exit_mult_str = f" (Implied Exit EV/EBITDA: {exit_mult_v:.2f}x)" if (exit_mult_v is not None and pd.notna(exit_mult_v)) else ""

            # Dynamic Model Validation Checks for Terminal Economics
            chk_wacc_g = a.wacc > a.terminal_growth
            chk_roic_g = a.terminal_roic > a.terminal_growth
            chk_reinv_valid = 0.0 <= reinv_rate < 1.0
            chk_tv_conc = result["terminal_share"] <= 0.75

            b_wacc_cls = "term-badge-pass" if chk_wacc_g else "term-badge-fail"
            b_wacc_txt = "PASS" if chk_wacc_g else "FAIL"
            b_roic_cls = "term-badge-pass" if chk_roic_g else "term-badge-warn"
            b_roic_txt = "PASS" if chk_roic_g else "WARN"
            b_reinv_cls = "term-badge-pass" if chk_reinv_valid else "term-badge-warn"
            b_reinv_txt = f"PASS ({reinv_rate:.1%})" if chk_reinv_valid else "WARN"
            b_conc_cls = "term-badge-pass" if chk_tv_conc else "term-badge-warn"
            b_conc_txt = "PASS (≤75%)" if chk_tv_conc else "HIGH (>75%)"

            st.markdown(
                f"""
                <div class="dcf-panel-card">
                    <div class="term-sub-header">A. Forecast &amp; Terminal Parameters</div>
                    <div class="term-kv-row">
                        <span class="t-label">Explicit Forecast Horizon</span>
                        <span class="t-val">{len(f)} Years ({first_year}–{first_year + len(f) - 1})</span>
                    </div>
                    <div class="term-kv-row">
                        <span class="t-label">Terminal Growth Rate (g)</span>
                        <span class="t-val">{a.terminal_growth:.2%}</span>
                    </div>
                    <div class="term-kv-row">
                        <span class="t-label">Terminal Return on Invested Capital (ROIC)</span>
                        <span class="t-val">{a.terminal_roic:.2%}</span>
                    </div>
                    <div class="term-kv-row">
                        <span class="t-label">Terminal Reinvestment Rate (g / ROIC)</span>
                        <span class="t-val">{reinv_rate:.1%}</span>
                    </div>
                    <div class="term-kv-row">
                        <span class="t-label">Weighted Average Cost of Capital (WACC)</span>
                        <span class="t-val">{a.wacc:.2%}</span>
                    </div>
                    <div class="term-sub-header">B. Terminal Value Calculation (IDR billion)</div>
                    <div class="term-kv-row">
                        <span class="t-label">Terminal Year-6 NOPAT</span>
                        <span class="t-val">IDR {term_nopat_v:,.1f} bn</span>
                    </div>
                    <div class="term-kv-row">
                        <span class="t-label">Less: Sustainable Terminal Reinvestment</span>
                        <span class="t-val">(IDR {term_reinv_amt:,.1f} bn)</span>
                    </div>
                    <div class="term-kv-row">
                        <span class="t-label">Terminal Free Cash Flow to Firm (FCFF)</span>
                        <span class="t-val">IDR {term_fcff_v:,.1f} bn</span>
                    </div>
                    <div class="term-kv-row">
                        <span class="t-label">Undiscounted Terminal Value at Year 5{exit_mult_str}</span>
                        <span class="t-val">IDR {term_val_v:,.1f} bn</span>
                    </div>
                    <div class="term-kv-row term-highlight">
                        <span class="t-label">Present Value of Terminal Value</span>
                        <span class="t-val" style="color:#087F69;">IDR {pv_term_v:,.1f} bn</span>
                    </div>
                    <div class="term-sub-header">C. Terminal Value Contribution to EV</div>
                    <div class="term-prop-wrap">
                        <div style="display:flex; justify-content:space-between; font-size:12.5px; font-weight:600; color:#1D1D1F;">
                            <span>Terminal Value Contribution</span>
                            <span style="color:#087F69;">{tv_share_pct:.1f}% of EV</span>
                        </div>
                        <div class="term-prop-bar-bg">
                            <div class="term-prop-bar-fcff" style="width:{fcff_share_pct:.1f}%;"></div>
                            <div class="term-prop-bar-tv" style="width:{tv_share_pct:.1f}%;"></div>
                        </div>
                        <div class="term-prop-legend">
                            <span>Explicit 5Y FCFF: {fcff_share_pct:.1f}% (IDR {pv_flows_v:,.1f} bn)</span>
                            <span>Terminal Value: {tv_share_pct:.1f}% (IDR {pv_term_v:,.1f} bn)</span>
                        </div>
                    </div>
                    <div class="term-sub-header">D. Model Validation &amp; Perpetuity Checks</div>
                    <div class="term-val-grid">
                        <div class="term-val-item">
                            <span>WACC &gt; Terminal Growth (g)</span>
                            <span class="{b_wacc_cls}">{b_wacc_txt}</span>
                        </div>
                        <div class="term-val-item">
                            <span>Terminal ROIC &gt; Terminal g</span>
                            <span class="{b_roic_cls}">{b_roic_txt}</span>
                        </div>
                        <div class="term-val-item">
                            <span>Valid Reinvestment (g / ROIC)</span>
                            <span class="{b_reinv_cls}">{b_reinv_txt}</span>
                        </div>
                        <div class="term-val-item">
                            <span>TV Share Bounds (≤75% EV)</span>
                            <span class="{b_conc_cls}">{b_conc_txt}</span>
                        </div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # ── EXPANDABLE EVIDENCE: 5-YEAR CONNECTED FINANCIAL STATEMENTS ──
        with st.expander("5-Year Connected Financial Statements (Income Statement · Balance Sheet · Cash Flow)", expanded=False):
            st.caption("Forecasted 5-year financial statements derived from the operational and macroeconomic drivers configured in Valuation Assumptions.")
            income_rows = ["revenue", "cogs", "opex", "da", "ebitda", "ebit", "nopat", "interest", "tax", "net_income"]
            bs_rows = ["cash", "ar", "inventory", "other_ca", "ppe", "other_assets", "assets", "ap", "other_cl", "short_debt", "long_debt", "other_liabilities", "liabilities", "equity", "balance_check"]
            cf_rows = ["net_income", "da", "delta_nwc", "cfo", "capex", "cfi", "funding", "repayment", "dividends", "cff", "cash_change", "cash", "fcff", "reinvestment", "invested_capital", "roic"]
            labels = BASE_FIELDS | {
                "ebitda": "EBITDA", "ebit": "EBIT", "nopat": "NOPAT (After-tax operating profit)", "assets": "Total assets",
                "ap": "Trade payables (Operating liability)",
                "other_cl": "Other operating current liabilities (Operating liability)",
                "short_debt": "Short-term debt (Financial debt)",
                "long_debt": "Long-term debt (Financial debt)",
                "liabilities": "Total liabilities", "balance_check": "Balance check",
                "delta_nwc": "Increase in operating working capital", "cfo": "Operating cash flow", "capex": "Capital expenditure (outflow)",
                "cfi": "Investing cash flow", "funding": "New borrowing / funding need", "repayment": "Debt repayment (outflow)",
                "dividends": "Dividends (outflow)", "cff": "Financing cash flow", "cash_change": "Net cash movement",
                "fcff": "Free cash flow to firm", "reinvestment": "Total Reinvestment (Net CapEx + ΔNWC)",
                "invested_capital": "Operating Invested Capital", "roic": "Return on Invested Capital (ROIC)"
            }
            hl_set = [
                "Reported revenue", "EBITDA", "EBIT", "NOPAT (After-tax operating profit)",
                "Net income", "Total assets", "Total liabilities", "Operating cash flow",
                "Capital expenditure (outflow)", "Free cash flow to firm", "Return on Invested Capital (ROIC)"
            ]
            sub_set = ["Net income", "Total assets", "Total liabilities", "Total common equity", "Free cash flow to firm"]
            for title, rows in [("Income Statement", income_rows), ("Balance Sheet", bs_rows), ("Cash Flow & Funding", cf_rows)]:
                df_fc = f[rows].T.rename(index=labels)
                st.markdown(
                    render_apple_table(
                        df_fc,
                        title=f"5-Year Forecast · {title}",
                        unit_label="Unit: IDR billion · 5-Year Explicit Horizon",
                        is_transposed_periods=True,
                        highlight_rows=hl_set,
                        subtotal_rows=sub_set,
                        default_format="{:,.1f}",
                    ),
                    unsafe_allow_html=True,
                )
                if title == "Balance sheet":
                    st.caption(
                        "**Liabilities Decomposition**: Financial debt (Short-term & Long-term debt) is maintained under a constant rollover "
                        "assumption. The increase in Total Liabilities is driven by spontaneous operating liabilities (Trade Payables "
                        "and Other Current Liabilities) scaling proportionately with revenue growth."
                    )
                elif title == "Cash flow & funding":
                    st.caption(
                        "**Financing Cash Flow Note**: Under the debt rollover assumption, scheduled debt repayment defaults to zero "
                        "(debt is rolled over at maturity). New borrowing is an automatic liquidity revolver that only activates if operating "
                        "cash flow is insufficient to cover CapEx, dividends, and the minimum cash buffer (2% of revenue)."
                    )

        # ── EXPANDABLE EVIDENCE: MATHEMATICAL PROOF OF CALCULATION ──
        with st.expander("Proof of Calculation · Mathematical Formulas & Live Audit", expanded=False):
            st.latex(r"\text{FCFF}_t = \text{EBIT}_t \times (1 - \tau) + \text{D\&A}_t - \text{CapEx}_t - \Delta \text{NWC}_t")
            st.latex(r"\text{TV}_5 = \frac{\text{NOPAT}_5 \times (1 + g) \times \left(1 - \frac{g}{\text{ROIC}_n}\right)}{\text{WACC} - g}")
            st.latex(r"\text{Implied Equity Value} = \sum_{t=1}^{5} \frac{\text{FCFF}_t}{(1 + \text{WACC})^t} + \frac{\text{TV}_5}{(1 + \text{WACC})^5} + \text{Cash}_0 + \text{NonOp}_0 - \text{Debt}_0 - \text{Claims}_0")
    else:
        st.warning("Review WACC, terminal growth, terminal ROIC, shares, and Year-5 earnings to calculate DCF.")

with scenario_tab:
    st.subheader("Scenario Analysis & Sensitivity Matrix")
    st.caption(
        "Evaluate intrinsic valuation dispersion across Bear, Base, and Bull operating cases, "
        "alongside 2D sensitivity to WACC and terminal growth."
    )
    if result:
        # ── SCENARIO KPI CARDS ──
        sc_k1, sc_k2, sc_k3, sc_k4, sc_k5 = st.columns(5)
        sc_k1.metric("Observed Market Price", fmt_idr(price, default="N/A"), "Reference Quote")
        sc_k2.metric(
            "Bear Case Target",
            fmt_idr(bear_p, default="N/A"),
            f"{((bear_p / price - 1.0) if (bear_p and price and price > 0) else 0.0):+.1%} vs. Market ({norm_probs.get('Bear', 0.25):.0%} prob)",
        )
        sc_k3.metric(
            "Base Case Target",
            fmt_idr(base_dcf_price, default="N/A"),
            f"{((base_dcf_price / price - 1.0) if (base_dcf_price and price and price > 0) else 0.0):+.1%} vs. Market ({norm_probs.get('Base', 0.50):.0%} prob)",
        )
        sc_k4.metric(
            "Bull Case Target",
            fmt_idr(bull_p, default="N/A"),
            f"{((bull_p / price - 1.0) if (bull_p and price and price > 0) else 0.0):+.1%} vs. Market ({norm_probs.get('Bull', 0.25):.0%} prob)",
        )
        sc_k5.metric(
            "Expected (Weighted) DCF",
            fmt_idr(expected_dcf_price, default="N/A"),
            f"{((expected_dcf_price / price - 1.0) if (expected_dcf_price and price and price > 0) else 0.0):+.1%} vs. Market",
        )

        sc_col_left, sc_col_right = st.columns([1.05, 1], gap="medium")
        with sc_col_left:
            st.markdown("#### Observed Market Price vs. Scenario Target Prices")
            sc_labels_tab = []
            sc_vals_tab = []
            sc_colors_tab = []
            if price and pd.notna(price):
                sc_labels_tab.append("Observed Market Price")
                sc_vals_tab.append(float(price))
                sc_colors_tab.append("#6E6E73")

            def _fmt_prob(p):
                pct = p * 100.0
                return f"{pct:.1f}%" if pct % 1 != 0 else f"{pct:.0f}%"

            if bear_p:
                sc_labels_tab.append(f"Bear ({_fmt_prob(norm_probs.get('Bear', 0.25))})")
                sc_vals_tab.append(float(bear_p))
                sc_colors_tab.append("#B25000")
            if base_dcf_price:
                sc_labels_tab.append(f"Base ({_fmt_prob(norm_probs.get('Base', 0.50))})")
                sc_vals_tab.append(float(base_dcf_price))
                sc_colors_tab.append("#0066CC")
            if bull_p:
                sc_labels_tab.append(f"Bull ({_fmt_prob(norm_probs.get('Bull', 0.25))})")
                sc_vals_tab.append(float(bull_p))
                sc_colors_tab.append("#1A7F37")
            if expected_dcf_price:
                sc_labels_tab.append("Expected Weighted")
                sc_vals_tab.append(float(expected_dcf_price))
                sc_colors_tab.append("#087F69")

            fig_scen_tab = go.Figure(go.Bar(
                x=sc_labels_tab,
                y=sc_vals_tab,
                marker_color=sc_colors_tab,
                text=[fmt_idr(v) for v in sc_vals_tab],
                textposition="outside",
                cliponaxis=False,
            ))
            if price and pd.notna(price):
                fig_scen_tab.add_hline(y=float(price), line_dash="dash", line_color="#1D1D1F", line_width=1.5)
            chart(fig_scen_tab, "IDR / share")

        with sc_col_right:
            st.markdown("#### 2D Sensitivity · Value / Share (WACC vs. Terminal Growth)")
            heat = go.Figure(go.Heatmap(
                z=grid.to_numpy(),
                x=list(grid.columns),
                y=list(grid.index),
                colorscale=[[0, "#E8F5F1"], [1, "#087F69"]],
                texttemplate="%{z:,.0f}",
                hovertemplate="Growth %{x}<br>WACC %{y}<br>Rp %{z:,.0f}<extra></extra>",
                showscale=False,
            ))
            chart(heat, "WACC")

        st.markdown("#### Scenario Summary Table (Bear / Base / Bull / Expected)")
        table_rows = list(scenario_rows)
        if len(prices_by_scenario) == 3 and base_dcf_price and base_dcf_price > 0 and expected_dcf_price is not None:
            exp_rev = sum(r["Year 5 revenue"] * norm_probs.get(r["Scenario"], 0.0) for r in scenario_rows)
            exp_ebit = sum(r["Year 5 EBIT"] * norm_probs.get(r["Scenario"], 0.0) for r in scenario_rows)
            exp_wacc = sum(r["WACC"] * norm_probs.get(r["Scenario"], 0.0) for r in scenario_rows)
            exp_g = sum(r["Terminal growth"] * norm_probs.get(r["Scenario"], 0.0) for r in scenario_rows)
            exp_roic = sum(r["Terminal ROIC"] * norm_probs.get(r["Scenario"], 0.0) for r in scenario_rows)
            exp_upside = ((expected_dcf_price / base_dcf_price) - 1.0)

            expected_row = {
                "Scenario": "Expected (Weighted)",
                "Probability": 1.0,
                "Value / share": expected_dcf_price,
                "Upside / Downside": f"{exp_upside:+.1%}",
                "Year 5 revenue": exp_rev,
                "Year 5 EBIT": exp_ebit,
                "WACC": exp_wacc,
                "Terminal growth": exp_g,
                "Terminal ROIC": exp_roic,
            }
            table_rows.append(expected_row)

        scen_df = pd.DataFrame(table_rows).set_index("Scenario")
        format_dict = {
            "Probability": "{:.1%}",
            "Value / share": "Rp {:,.2f}",
            "Year 5 revenue": "IDR {:,.1f} bn",
            "Year 5 EBIT": "IDR {:,.1f} bn",
            "WACC": "{:.2%}",
        }
        if "Terminal growth" in scen_df.columns:
            format_dict["Terminal growth"] = "{:.2%}"
        if "Terminal ROIC" in scen_df.columns:
            format_dict["Terminal ROIC"] = "{:.2%}"

        st.markdown(
            render_apple_table(
                scen_df,
                title="Scenario Valuation Matrix & Operating Case Trajectory",
                unit_label="Unit: IDR / Share · Expected Value Synthesis",
                final_rows=["Expected"],
                highlight_rows=["Base", "Expected"],
                col_formats={
                    "Probability": "{:.1%}",
                    "Value / share": "Rp {:,.2f}",
                    "Year 5 revenue": "IDR {:,.1f} bn",
                    "Year 5 EBIT": "IDR {:,.1f} bn",
                    "WACC": "{:.2%}",
                    "Terminal growth": "{:.2%}",
                    "Terminal ROIC": "{:.2%}",
                },
            ),
            unsafe_allow_html=True,
        )

        st.button("Edit scenario drivers", key="btn_edit_scenario_drivers")
        components.html(
            """
            <script>
                const parentDoc = window.parent.document;
                if (!parentDoc._scenarioNavInitialized) {
                    parentDoc._scenarioNavInitialized = true;
                    parentDoc.addEventListener('click', (e) => {
                        const btn = e.target.closest('.st-key-btn_edit_scenario_drivers button');
                        if (btn) {
                            const tabs = Array.from(parentDoc.querySelectorAll('button[data-testid="stTab"], [role="tab"]'));
                            const targetTab = tabs.find(t => t.innerText && t.innerText.includes("Valuation assumptions"));
                            if (targetTab) {
                                targetTab.click();
                                let attempts = 0;
                                const interval = setInterval(() => {
                                    attempts++;
                                    const el = parentDoc.getElementById('section-04-scenario-modeling')
                                            || Array.from(parentDoc.querySelectorAll('h4, div, span')).find(x => x.innerText && x.innerText.includes('04 · Scenario modeling'));
                                    if (el) {
                                        el.scrollIntoView({ behavior: 'smooth', block: 'start' });
                                        clearInterval(interval);
                                    } else if (attempts > 20) {
                                        clearInterval(interval);
                                    }
                                }, 50);
                            }
                        }
                    }, true);
                }
            </script>
            """,
            height=0,
            width=0,
        )
    else:
        st.warning("Review WACC, terminal growth, terminal ROIC, shares, and Year-5 earnings to calculate Scenario & Sensitivity outputs.")

with final_interp_tab:
    st.subheader("Final Valuation Interpretation & Decision Synthesis")
    st.caption("Concise synthesis of intrinsic DCF, market-implied Relative Valuation, blended fair-value range, and investment thesis.")

    fi_range_str = f"Rp {fv_low:,.0f} – Rp {fv_high:,.0f}" if (fv_low is not None and fv_high is not None) else "N/A"
    fi_blend_str = f"Rp {blended_price:,.0f}" if blended_price is not None else "N/A"
    fi_dcf_str = f"Rp {dcf_p:,.0f}" if dcf_p is not None else "N/A"
    fi_rel_str = f"Rp {rel_price:,.0f}" if pd.notna(rel_price) else "N/A (< 2 valid peers)"
    fi_up_str = f"{upside_pct:+.1%}" if upside_pct is not None else "N/A"

    st.markdown(
        f"""
        <div class="ios-card-hero" style="margin-bottom:16px;">
            <div style="font-size:0.76rem; font-weight:700; text-transform:uppercase; letter-spacing:0.06em; color:#087F69; margin-bottom:6px;">
                Final Valuation Synthesis · {clean_name} ({c['symbol']})
            </div>
            <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap:16px; margin-top:8px;">
                <div>
                    <div style="font-size:0.74rem; color:#6E6E73; font-weight:600; text-transform:uppercase;">Blended Fair Value</div>
                    <div style="font-size:1.65rem; font-weight:800; color:#1D1D1F; font-variant-numeric:tabular-nums;">{fi_blend_str}</div>
                    <div style="font-size:0.78rem; color:#6E6E73;">Weighting: {eff_w_dcf:.0%} DCF / {eff_w_rel:.0%} Relative</div>
                </div>
                <div>
                    <div style="font-size:0.74rem; color:#6E6E73; font-weight:600; text-transform:uppercase;">Observed Market Price</div>
                    <div style="font-size:1.65rem; font-weight:800; color:#1D1D1F; font-variant-numeric:tabular-nums;">{fmt_idr(price, default='N/A')}</div>
                    <div style="font-size:0.78rem; color:#6E6E73;">Implied Upside / Downside: <b>{fi_up_str}</b></div>
                </div>
                <div>
                    <div style="font-size:0.74rem; color:#6E6E73; font-weight:600; text-transform:uppercase;">Fair-Value Range</div>
                    <div style="font-size:1.35rem; font-weight:800; color:#1D1D1F; font-variant-numeric:tabular-nums; margin-top:4px;">{fi_range_str}</div>
                    <div style="font-size:0.78rem; color:#6E6E73;">DCF ({fi_dcf_str}) · Relative ({fi_rel_str})</div>
                </div>
                <div>
                    <div style="font-size:0.74rem; color:#6E6E73; font-weight:600; text-transform:uppercase;">Action Recommendation</div>
                    <div style="margin-top:6px;"><span class="ios-pill {rec_pill_cls}" style="font-size:0.95rem; padding:6px 14px;">{rec_rating}</span></div>
                    <div style="font-size:0.76rem; color:#6E6E73; margin-top:6px;">Criteria: BUY &gt; +15% · HOLD ±15% · SELL &lt; −15%</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.expander("Why This Valuation Approach? · Method Suitability & Weighting Rationale", expanded=True):
        st.markdown(
            f"""
            - **Effective Method Weighting**: **{eff_w_dcf:.0%} DCF / {eff_w_rel:.0%} Relative** (Peer Group Quality: **{approach_eval.get('quality', 'Standard')}**)
            - **Business & Cash-Flow Characteristics**: {clean_name} operates in **{c.get('industry', 'General')}** with base revenue of **IDR {b['revenue']:,.1f} bn**, EBITDA margin of **{target_profile['ebitda_margin']:.1%}**, and Year-5 forecast FCFF of **IDR {(float(f.loc[f.index[-1], 'fcff']) if not f.empty else 0.0):,.1f} bn**.
            - **Capital Structure & Solvency**: Opening Debt-to-Equity (DER) is **{target_profile['der']:.2f}x** (Net Debt IDR {(b['short_debt'] + b['long_debt'] - b['cash']):,.1f} bn). FCFF DCF values the enterprise independent of leverage changes, while EV/EBITDA and EV/EBIT multiples neutralize capital-structure differences across peers.
            - **Peer Comparability**: **{len(peer_rows)}** active IDX peer(s) meet positive-multiple criteria ({'sufficient for relative triangulation' if len(peer_rows) >= 2 else 'below the 2-peer policy minimum, automatically assigning 100% weight to DCF'}).
            """
        )
        st.caption(f"• {approach_eval.get('rationale', '')}")

    st.info("To review the formatted institutional report or export the PDF Research Report and 9-sheet Excel Workbook, open the **Research Report** section at the top of the workspace.")


# ═════════════════════════════════════════════════════════════════════════════
# SECTION 3: RESEARCH REPORT & EXPORT
# ═════════════════════════════════════════════════════════════════════════════
with report_tab:
    st.markdown(
        '<div class="page-context-banner">'
        '<span class="page-context-title">Research Report — Results & Export</span>'
        '<span class="page-context-desc">Review valuation conclusions, methodology, key risks, and downloadable reports.</span>'
        '</div>',
        unsafe_allow_html=True,
    )
    st.subheader("Institutional Equity Research Report & Deliverables Export")
    st.caption(
        f"Valuation report for {clean_name} ({c['symbol']}) · "
        f"Base Fiscal Period: {period} · Currency: IDR billions (Rp per share)."
    )

    # ── Export Bar at Top for Convenience ──
    clean_sym = c["symbol"].replace(".JK", "").upper()
    rep_exp_col1, rep_exp_col2 = st.columns(2, gap="medium")
    if result:
        with rep_exp_col1:
            if pdf_report_bytes is not None:
                st.download_button(
                    "Download PDF Report",
                    data=pdf_report_bytes,
                    file_name=f"{clean_sym}_Valuation_Report.pdf",
                    mime="application/pdf",
                    type="primary",
                    use_container_width=True,
                    on_click="ignore",
                    key=key("dl_pdf_report_tab"),
                )
        with rep_exp_col2:
            if excel_bytes is not None:
                st.download_button(
                    "Download Excel Dashboard",
                    data=excel_bytes,
                    file_name=f"{clean_sym}_Valuation_Dashboard.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                    on_click="ignore",
                    key=key("dl_xlsx_report_tab"),
                )
    else:
        st.warning("Complete DCF valuation inputs to enable PDF and Excel exports.")

    st.divider()

    # ── 1. EXECUTIVE SUMMARY ──
    st.markdown('<div class="ios-sub-header" style="margin-top:4px;">1. Executive Summary</div>', unsafe_allow_html=True)
    st.markdown(
        f"""
        <div class="ios-card" style="padding:18px;">
            <div style="font-size:0.92rem; color:#1D1D1F; line-height:1.65;">
                <b>{clean_name} ({c['symbol']})</b> is classified under IDX-IC <b>{c.get('sector', 'IDX Sector')} — {c.get('industry', 'General')}</b>
                with latest audited base fiscal period <b>{period}</b>. Based on a 5-year explicit Free Cash Flow to Firm (FCFF) DCF model
                and comparable IDX peer multiples, we estimate a <b>Blended Fair Value of {fmt_idr(blended_price, default='N/A')} per share</b>
                ({eff_w_dcf:.0%} DCF / {eff_w_rel:.0%} Relative) compared against the observed reference market price of <b>{fmt_idr(price, default='N/A')} per share</b>,
                implying <b>{f'{upside_pct:+.1%}' if upside_pct is not None else 'N/A'}</b> upside/downside and supporting a <b>{rec_rating}</b> recommendation
                within an estimated fair-value range of <b>{f'Rp {fv_low:,.0f} – Rp {fv_high:,.0f}' if (fv_low and fv_high) else 'N/A'}</b>.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── 2. FINANCIAL VALUATION SUMMARY ──
    st.markdown('<div class="ios-sub-header">2. Financial Valuation Summary (DCF · Relative · Scenarios)</div>', unsafe_allow_html=True)
    val_summary_rows = [
        {
            "Valuation Pillar": "Observed Market Price (Reference)",
            "Implied Value / Share": fmt_idr(price, default="N/A"),
            "Vs. Market Price": "0.0% (Benchmark)",
            "Effective Weight": "—",
            "Methodology & Basis": f"Latest market reference quote · {fmt_shares(shares)} diluted shares",
        },
        {
            "Valuation Pillar": "Intrinsic DCF (Base Case)",
            "Implied Value / Share": fmt_idr(base_dcf_price, default="N/A"),
            "Vs. Market Price": f"{((base_dcf_price / price - 1.0) if (base_dcf_price and price and price > 0) else 0.0):+.1%}",
            "Effective Weight": "—",
            "Methodology & Basis": f"5-year explicit FCFF + Year-6 perpetuity (WACC {a.wacc:.2%}, g {a.terminal_growth:.2%}, ROIC {a.terminal_roic:.2%})",
        },
        {
            "Valuation Pillar": "Intrinsic DCF (Probability-Weighted Expected)",
            "Implied Value / Share": fmt_idr(dcf_p, default="N/A"),
            "Vs. Market Price": f"{((dcf_p / price - 1.0) if (dcf_p and price and price > 0) else 0.0):+.1%}",
            "Effective Weight": f"{eff_w_dcf:.1%}",
            "Methodology & Basis": f"Bear ({norm_probs.get('Bear', 0.25):.0%}) / Base ({norm_probs.get('Base', 0.50):.0%}) / Bull ({norm_probs.get('Bull', 0.25):.0%}) weighted intrinsic value",
        },
        {
            "Valuation Pillar": f"Relative Valuation ({rel_agg_choice})",
            "Implied Value / Share": fmt_idr(rel_price, default="N/A (< 2 peers)") if pd.notna(rel_price) else "N/A (< 2 peers)",
            "Vs. Market Price": f"{((rel_price / price - 1.0) if (pd.notna(rel_price) and price and price > 0) else 0.0):+.1%}" if pd.notna(rel_price) else "—",
            "Effective Weight": f"{eff_w_rel:.1%}",
            "Methodology & Basis": f"Weighted across eligible EV/EBITDA, EV/EBIT, P/E, P/BV multiples ({len(peer_rows)} active peers)",
        },
        {
            "Valuation Pillar": "Blended Fair Value Target",
            "Implied Value / Share": fmt_idr(blended_price, default="N/A"),
            "Vs. Market Price": fmt_pct(upside_pct, signed=True, default="—"),
            "Effective Weight": "100.0%",
            "Methodology & Basis": f"Recommendation: {rec_rating} (BUY > +15%, HOLD ±15%, SELL < −15%)",
        },
    ]
    st.markdown(
        render_apple_table(
            pd.DataFrame(val_summary_rows),
            title="Valuation Architecture Summary & Blended Fair Value",
            unit_label="Target Fair Value Synthesis",
            hide_index=True,
            final_rows=["Blended Fair Value Target"],
            highlight_rows=["DCF Intrinsic Fair Value (FCFF)", "Blended Fair Value Target"],
            col_alignments={
                "Valuation Pillar": "col-text",
                "Implied Value / Share": "col-num",
                "Vs. Market Price": "col-num",
                "Effective Weight": "col-num",
                "Methodology & Basis": "col-text",
            },
        ),
        unsafe_allow_html=True,
    )

    # ── 3. METHOD SELECTION RATIONALE ──
    st.markdown('<div class="ios-sub-header">3. Method Selection & Peer Comparability Rationale</div>', unsafe_allow_html=True)
    st.markdown(
        f"""
        <div class="ios-card" style="padding:16px; font-size:0.86rem; color:#1D1D1F; line-height:1.6;">
            <div>• <b>Primary Valuation Architecture</b>: Triangulates <b>FCFF Discounted Cash Flow ({eff_w_dcf:.0%})</b> with <b>Comparable Peer Multiples ({eff_w_rel:.0%})</b> (Peer Group Quality: <b>{approach_eval.get('quality', 'Standard')}</b>). {approach_eval.get('rationale', '')}</div>
            <div>• <b>Why FCFF DCF</b>: Captures multi-year operating margin transitions ({a.ebit_margin:.1%} in Y1–3 to {a.mature_margin:.1%} in Y5), explicit working-capital and CapEx reinvestment ({a.capex_pct:.1%} of sales), and enforces Damodaran's terminal reinvestment discipline (g / ROIC).</div>
            <div>• <b>Why Comparable Multiples</b>: Anchors intrinsic assumptions against observable IDX market pricing across {len(peer_rows)} active peer(s) ranked by Euclidean distance on EBITDA margin and Debt/Equity (DER).</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── 4. KEY ASSUMPTIONS ──
    st.markdown('<div class="ios-sub-header">4. Key Valuation Assumptions & Provenance</div>', unsafe_allow_html=True)
    st.markdown(
        render_apple_table(
            pd.DataFrame(assump_audit_rows),
            title="Comprehensive Valuation Assumptions Audit & Provenance Log",
            unit_label="Economic Drivers & Method Calibration",
            hide_index=True,
            col_alignments={
                "Category": "col-text",
                "Parameter": "col-text",
                "Effective Value": "col-num",
                "Inferred Default": "col-num",
                "Provenance": "col-center",
                "Economic Rationale": "col-text",
            },
            badge_cols={
                "Provenance": {"User Override": "warn", "Model Inferred": "info", "Policy Default": "info"},
            },
        ),
        unsafe_allow_html=True,
    )

    # ── 5. KEY RISKS & MODEL LIMITATIONS ──
    st.markdown('<div class="ios-sub-header">5. Key Investment Risks & Structural Model Limitations</div>', unsafe_allow_html=True)
    rep_rk1, rep_rk2 = st.columns(2, gap="medium")
    with rep_rk1:
        st.markdown(
            f"""
            <div class="ios-card" style="padding:16px; font-size:0.84rem; line-height:1.6;">
                <div style="font-weight:700; color:#B25000; text-transform:uppercase; font-size:0.75rem; margin-bottom:6px;">Key Investment & Execution Risks</div>
                <div>• <b>Terminal Value Concentration</b>: Terminal value accounts for <b>{tv_share:.1%}</b> of Enterprise Value.</div>
                <div>• <b>Operating & Margin Execution</b>: Sensitivity to achieving {a.growth:.1%} near-term growth and {a.mature_margin:.1%} mature EBIT margin.</div>
                <div>• <b>Capital Structure & Refinancing</b>: Opening DER of <b>{target_profile['der']:.2f}x</b> and cumulative 5-year new borrowing of <b>IDR {funding:,.1f} bn</b>.</div>
                <div>• <b>Macro & Discount Rate</b>: Sensitivity to 10Y IndoGB risk-free rate ({a.risk_free:.2%}), equity beta ({a.beta:.2f}), and CRP ({a.country_risk_premium:.2%}).</div>
                <div>• <b>FY2025 Baseline Anchor</b>: Forecasts anchor on audited FY{period} figures; post-FY2025 unreflected corporate events or interim swings are not modeled in baseline inputs.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with rep_rk2:
        st.markdown(
            f"""
            <div class="ios-card" style="padding:16px; font-size:0.84rem; line-height:1.6;">
                <div style="font-weight:700; color:#6E6E73; text-transform:uppercase; font-size:0.75rem; margin-bottom:6px;">Verified Model Boundaries & Limitations</div>
                <div>• <b>5-Year Explicit Horizon</b>: Annual forecast covers 5 explicit years followed by a single-stage Year-6 perpetuity.</div>
                <div>• <b>Constant WACC & Year-End Discounting</b>: Applies a constant WACC ({a.wacc:.2%}) without stub-period roll-forward from {period}.</div>
                <div>• <b>Simplified Revolver & Tax</b>: Shortfalls draw short-term revolver debt to maintain a 2% cash buffer; no NOL tax carryforward schedule.</div>
                <div>• <b>Data Source Coverage</b>: Standardized Yahoo Finance (`yfinance`) annual filings for non-financial operating issuers.</div>
                <div>• <b>FY2025 Baseline Anchor</b>: Projections start after fiscal {period} without rolling interim stub-period adjustments.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # ── 6. VALIDATION & INTEGRITY AUDIT ──
    st.markdown('<div class="ios-sub-header">6. Model Validation & Integrity Summary</div>', unsafe_allow_html=True)
    st.markdown(
        render_apple_table(
            pd.DataFrame(validation_checks),
            title="Automated Model Integrity & Validation Checks",
            unit_label="Rigorous Pre-Flight Audit",
            hide_index=True,
            col_alignments={
                "Check ID": "col-center",
                "Validation Rule": "col-text",
                "Status": "col-center",
                "Measured Value": "col-num",
                "Threshold / Standard": "col-text",
            },
            badge_cols={
                "Status": {"PASS": "pass", "FAIL": "fail", "WARNING": "warn", "NOT VERIFIED": "info"},
            },
        ),
        unsafe_allow_html=True,
    )


with st.sidebar:
    st.divider()
    st.markdown("### Keep your work")
    analysis_name = st.text_input("Analysis name", value=f"{c['symbol']} · Base case", key=key("analysis_name"))
    payload = dict(company=pack_company(c), base=b, assumptions=asdict(a), drivers=drivers.to_dict(orient="list"), shares=shares, price=price, fx=fx, peers=peer_rows)
    if st.button("Save analysis", width="stretch"):
        try:
            storage.save(analysis_name, payload)
            st.success("Saved on this PC. Open it under Saved analyses.")
        except (ValueError, TypeError) as exc:
            st.error(f"Could not save: {exc}")
    if result:
        download = workbook(
            company=c,
            historical=historical,
            base=b,
            assumptions=a,
            drivers=drivers,
            forecast=f,
            result=result,
            grid=grid,
            peers=peer_rows,
            relative=relative,
            expected_dcf_price=expected_dcf_price,
            rel_price=rel_price,
            blended_price=blended_price,
            rec=rec,
            scenario_rows=scenario_rows,
            mult_weights=mult_weights_norm,
            rel_breakdown=rel_breakdown,
        )
        st.download_button("Export Excel snapshot", download, file_name=f"{c['symbol']}_valuation.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", width="stretch")
    st.caption("Refresh data")
    if st.button("Clear cached Yahoo data", width="stretch"):
        get_company.clear()
        st.success("Cache cleared. Load the ticker again to fetch new data.")

st.caption("NUSA / IDX VALUATION LAB    ·    IDR billions unless stated    ·    Institutional Equity Research Workspace")
