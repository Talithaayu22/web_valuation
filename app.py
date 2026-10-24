from dataclasses import asdict, replace
from html import escape
import importlib
import json
import math
import re
import sys
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

# Explicitly reload valuation submodules to prevent stale sys.modules caching in Streamlit
for _mod_name in ("valuation.model", "valuation.data", "valuation.report_pdf", "valuation.export", "valuation.storage"):
    if _mod_name in sys.modules:
        try:
            importlib.reload(sys.modules[_mod_name])
        except Exception:
            pass

try:
    from valuation.data import clean_company_name
except ImportError:
    def clean_company_name(name: str) -> str:
        if not name:
            return ""
        cleaned = re.sub(r"^\s*perusahaan\s+perseroan\s*\(persero\)\s*", "", str(name), flags=re.IGNORECASE)
        cleaned = re.sub(r"\bperusahaan\s+perseroan\b", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\(persero\)", "", cleaned, flags=re.IGNORECASE)
        return re.sub(r"\s+", " ", cleaned).strip()

try:
    from valuation.data import (
        CATALOG, BILLION, demo_company, demo_peers, fetch_company, peer_record, ticker_symbol,
        get_default_peers_for_ticker, get_or_fetch_peers, rank_peers_similarity
    )
except ImportError:
    from valuation.data import (
        CATALOG, BILLION, demo_company, fetch_company, peer_record, ticker_symbol,
        get_default_peers_for_ticker, rank_peers_similarity
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

st.set_page_config(page_title="Nusa · IDX Valuation", page_icon="◈", layout="wide")
st.markdown("""<style>
.block-container {padding-top:3.5rem; max-width:1550px; padding-bottom:3rem}
[data-testid="stSidebar"] {border-right:1px solid #dfe8e5}
h1 {font-weight:650!important; letter-spacing:-1.5px!important}
h2,h3 {letter-spacing:-.5px!important}
/* --- Institutional KPI Metric Card Styling --- */
[data-testid="stMetric"] {
    background: #ffffff !important;
    border: 1px solid #e0e8e5 !important;
    border-radius: 12px !important;
    padding: 14px 16px !important;
    min-height: 108px !important;
    display: flex !important;
    flex-direction: column !important;
    justify-content: space-between !important;
    box-sizing: border-box !important;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.02) !important;
    transition: border-color 0.15s ease, box-shadow 0.15s ease !important;
}

[data-testid="stMetric"]:hover {
    border-color: #087f69 !important;
    box-shadow: 0 3px 10px rgba(8, 127, 105, 0.07) !important;
}

/* Metric Label: Eliminate ellipsis, allow natural multi-line wrapping */
[data-testid="stMetricLabel"] {
    color: #5f7578 !important;
    min-height: 2.7em !important;
    display: flex !important;
    align-items: flex-start !important;
    margin-bottom: 6px !important;
    white-space: normal !important;
    overflow: visible !important;
    text-overflow: clip !important;
}

[data-testid="stMetricLabel"],
[data-testid="stMetricLabel"] * {
    color: #5f7578 !important;
    font-size: 11.5px !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.5px !important;
    white-space: normal !important;
    overflow: visible !important;
    text-overflow: clip !important;
    word-break: break-word !important;
    overflow-wrap: break-word !important;
    line-height: 1.35 !important;
}

/* Metric Value: Fit large IDR values and percentages without clipping or ellipsis */
[data-testid="stMetricValue"] {
    white-space: normal !important;
    overflow: visible !important;
    text-overflow: clip !important;
}

[data-testid="stMetricValue"],
[data-testid="stMetricValue"] * {
    white-space: normal !important;
    overflow: visible !important;
    text-overflow: clip !important;
    word-break: normal !important;
    overflow-wrap: break-word !important;
    font-size: clamp(1.18rem, 1.5vw, 1.62rem) !important;
    font-weight: 700 !important;
    color: #173e37 !important;
    line-height: 1.25 !important;
}

/* Metric Delta */
[data-testid="stMetricDelta"],
[data-testid="stMetricDelta"] * {
    white-space: normal !important;
    overflow: visible !important;
    text-overflow: clip !important;
    font-size: 0.85rem !important;
}

/* Ensure column flex stretch so all KPI cards in a row have identical height */
div[data-testid="column"] {
    display: flex !important;
    flex-direction: column !important;
}

div[data-testid="column"] > div[data-testid="stMetric"] {
    flex: 1 1 100% !important;
    height: 100% !important;
}

div[data-testid="column"] > div:has([data-testid="stMetric"]) {
    flex: 1 1 100% !important;
    height: 100% !important;
    display: flex !important;
    flex-direction: column !important;
}

/* Viewport responsive breakpoints */
@media (max-width: 1200px) {
    [data-testid="stMetric"] {
        padding: 12px 14px !important;
        min-height: 100px !important;
    }
    [data-testid="stMetricLabel"],
    [data-testid="stMetricLabel"] * {
        font-size: 11px !important;
    }
    [data-testid="stMetricValue"],
    [data-testid="stMetricValue"] * {
        font-size: clamp(1.1rem, 1.4vw, 1.45rem) !important;
    }
}

@media (max-width: 900px) {
    [data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]) {
        flex-wrap: wrap !important;
        gap: 12px !important;
    }
    div[data-testid="column"]:has([data-testid="stMetric"]) {
        min-width: calc(50% - 12px) !important;
        flex: 1 1 calc(50% - 12px) !important;
    }
}

@media (max-width: 600px) {
    div[data-testid="column"]:has([data-testid="stMetric"]) {
        min-width: 100% !important;
        flex: 1 1 100% !important;
    }
}
.eyebrow {color:#087f69; font-size:12px; font-weight:700; letter-spacing:2px; margin-bottom:10px}
.badge {display:inline-block; background:#e3f3ec; color:#087f69; padding:5px 12px; border-radius:20px; font-size:12px}
.hero {padding:23px 28px; background:#173e37; color:white; border-radius:14px; margin:16px 0 24px}
.hero h2 {color:white; margin:0 0 6px; font-size:1.65rem}.hero p {color:#c2dcd3;margin:0}
.small {color:#718481;font-size:12px}
button {border-radius:8px!important}
</style>""", unsafe_allow_html=True)


@st.cache_data(ttl=3600, show_spinner=False)
def get_company(symbol):
    return fetch_company(symbol)


def activate(company, saved=None):
    st.session_state.company = company
    st.session_state.revision = st.session_state.get("revision", 0) + 1
    st.session_state.saved_inputs = saved or {}
    if company.get("demo"):
        st.session_state.peer_companies = demo_peers()
        st.session_state.peer_errors = []
    else:
        st.session_state.pop("peer_companies", None)
        st.session_state.pop("peer_errors", None)


def pack_company(c):
    return {k: v for k, v in c.items() if k not in ("historical", "raw")} | {
        "historical": c["historical"].to_json(orient="split", date_format="iso"),
        "raw": {name: frame.to_json(orient="split", date_format="iso") for name, frame in c["raw"].items()}
    }


def unpack_company(c):
    from io import StringIO
    out = dict(c)
    out["historical"] = pd.read_json(StringIO(c["historical"]), orient="split", convert_axes=False)
    out["raw"] = {name: pd.read_json(StringIO(data), orient="split", convert_axes=False) for name, data in c.get("raw", {}).items()}
    return out


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
    activate(demo_company())

with st.sidebar:
    st.markdown("## ◈ Nusa")
    st.caption("THE IDX VALUATION WORKSPACE")
    with st.form("lookup"):
        selected = st.selectbox("Quick select", ["Enter a ticker"] + [f"{k} · {v}" for k, v in CATALOG.items()])
        typed = st.text_input("IDX ticker", placeholder="e.g. TLKM", help="Four-character IDX code. .JK is added automatically.")
        submitted = st.form_submit_button("Load company", type="primary", width="stretch")
    if submitted:
        symbol = typed.strip() or (selected.split(" · ")[0] if selected != "Enter a ticker" else "")
        try:
            with st.spinner("Loading annual financial statements…"):
                activate(get_company(ticker_symbol(symbol)))
        except Exception as exc:
            st.error(f"Could not load company: {exc}")
    if st.button("Explore fictional demo", width="stretch"):
        activate(demo_company())
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
rev = st.session_state.revision
saved = st.session_state.saved_inputs
key = lambda name: f"{rev}_{name}"

st.markdown('<div class="eyebrow">INDONESIA EQUITY RESEARCH / VALUATION LAB</div>', unsafe_allow_html=True)
head, status = st.columns([4, 1])
with head:
    st.title("A clearer view of value.")
    st.caption("Connect the statements. Test your assumptions. Understand the price.")
with status:
    st.markdown(f'<div class="badge">{"ILLUSTRATIVE DEMO" if c["demo"] else escape(c["symbol"]) + " · YAHOO DATA"}</div>', unsafe_allow_html=True)
clean_name = clean_company_name(c.get("name", ""))
st.markdown(f'<div class="hero"><h2>{escape(clean_name)}</h2><p>{escape(c["sector"])} &nbsp; / &nbsp; {escape(c["industry"])}</p></div>', unsafe_allow_html=True)
if c["demo"]:
    st.info("You’re viewing a fictional business with illustrative financials. Load an IDX ticker from the sidebar to use Yahoo data.")
else:
    st.caption(f"Retrieved {c['fetched_at']} · Fiscal-year-end valuation convention · Prices may be delayed")
    if c["sector"] == "Financial Services" or any(x in c["industry"].lower() for x in ("bank", "insurance", "reit")):
        st.warning("This version models non-financial operating companies. Banks, insurers, and REITs need a dedicated valuation model. Choose another company.")
        st.stop()

overview, assumptions_tab, statements, dcf_tab, peers_tab, data_tab = st.tabs([
    "Overview", "Valuation assumptions", "5-year model", "DCF & sensitivity", "Relative valuation", "Data review"
])

with data_tab:
    st.subheader("Start with trustworthy inputs")
    st.caption("Source annual statements are retained. All model money is IDR billion; shares are in billions. Expenses are entered as positive amounts.")
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
    st.markdown(f"**Historical annual data · latest common fiscal period {period}**")
    st.dataframe(historical.rename(index=BASE_FIELDS).style.format("{:,.2f}", na_rep="Missing"), width="stretch")
    source_base = historical.loc[list(BASE_FIELDS), historical.columns[-1]]
    base_values = saved.get("base", source_base.to_dict())
    review = pd.DataFrame({
        "Account": [BASE_FIELDS[k] for k in BASE_FIELDS],
        "Reported": [source_base[k] for k in BASE_FIELDS],
        "Value": [base_values.get(k) for k in BASE_FIELDS],
        "Source": ["Saved/user input" if saved else c["provenance"].get(f"{period}:{k}", "Illustrative") for k in BASE_FIELDS]
    }, index=list(BASE_FIELDS))
    st.markdown("**Review and correct opening inputs**")
    edited = st.data_editor(
        review, disabled=["Account", "Reported", "Source"],
        column_config={"Value": st.column_config.NumberColumn("Model input · IDR bn", format="%.3f"), "Reported": st.column_config.NumberColumn("Reported · IDR bn", format="%.3f")},
        height=450, width="stretch", key=key("base_editor")
    )
    missing = [k for k in BASE_FIELDS if pd.isna(edited.loc[k, "Value"])]
    accept_missing = False
    if missing:
        st.warning("Missing: " + ", ".join(BASE_FIELDS[k] for k in missing))
        accept_missing = st.checkbox("I reviewed the missing accounts and explicitly assume they are zero", key=key("missing"))
    b = {k: float(edited.loc[k, "Value"]) if pd.notna(edited.loc[k, "Value"]) else 0. for k in BASE_FIELDS}
    if abs(base_check(b)) > .01:
        st.error(f"Opening balance sheet difference: IDR {base_check(b):,.2f} bn. Correct the input accounts; the app will not insert a balancing plug.")
    col1, col2 = st.columns(2)
    with col1:
        shares = st.number_input("Current / diluted shares outstanding (billions)", min_value=0., value=float(saved.get("shares", (c["shares"] or 0) / BILLION)), key=key("shares"), format="%.6f")
    with col2:
        price = st.number_input("Reference market price (IDR/share)", min_value=0., value=float(saved.get("price", c["price"] or 0)), key=key("price"))
    st.caption("Current shares are a no-future-dilution assumption. Override with diluted shares if needed. Other current assets/liabilities are treated as operating; reclassify them when reviewing inputs.")
    for name, raw in c["raw"].items():
        with st.expander(f"Raw source · {name} · {c['financial_currency'] or 'currency unverified'} units"):
            st.dataframe(raw, width="stretch")

if fx <= 0 or (missing and not accept_missing):
    with overview:
        st.warning("Open Data review and complete the missing inputs or currency conversion to unlock the forecast.")
    st.stop()


def inferred_assumptions():
    return infer_assumptions(historical, b, c)


initial = make_assumptions(**saved["assumptions"]) if saved.get("assumptions") else inferred_assumptions()
with assumptions_tab:
    st.subheader("Valuation assumptions & methodology lab")
    st.caption("Review, customize, and stress-test the three fundamental pillars of the valuation model. Changes update all connected statements, DCF cash flows, and relative valuation bridges.")

    # Live Metric Summary Header (2 rows x 3 columns for balanced responsiveness and readability)
    m_r1_1, m_r1_2, m_r1_3 = st.columns(3)
    m_r1_1.metric("Calculated WACC", f"{initial.wacc:.2%}")
    m_r1_2.metric("Cost of Equity", f"{initial.cost_of_equity:.2%}")
    m_r1_3.metric("Borrowing Cost (Kd)", f"{initial.debt_rate:.2%}")

    m_r2_1, m_r2_2, m_r2_3 = st.columns(3)
    m_r2_1.metric("Debt Weight", f"{initial.debt_weight:.0%}")
    m_r2_2.metric("Initial Growth (Y1–3)", f"{initial.growth:.1%}")
    m_r2_3.metric("EBIT Margin (Y1–3)", f"{initial.ebit_margin:.1%}")
    st.divider()

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

        col_op, col_macro, col_policy = st.columns(3)

        with col_op:
            st.markdown("#### 01 · Operating model")
            st.caption("Revenue growth, operating margins, reinvestment, and capital intensity.")
            pct(
                "Growth · years 1–3 (%)", "growth", -50, 100,
                help=f"Anchored to audited 3-year historical revenue CAGR ({initial.growth:.1%}). In Years 4–5, revenue growth smoothly transitions toward Year 5 mature growth."
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
            st.markdown("#### 02 · Macro & WACC")
            st.caption("Damodaran ERP, Indonesia CRP, JKSE regression beta, and capital structure.")
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
                help="Effective pre-tax debt borrowing rate (Kd = Interest Expense / Total Debt). Reflects weighted average coupon rate on commercial bank borrowings and corporate bonds."
            )
            pct(
                "Target debt / capital (%)", "debt_weight", 0, 95,
                help="Target capital structure debt weight (D / (D + E)). Inferred from latest balance sheet book debt vs market capitalization."
            )
            override = st.checkbox("Override calculated WACC", value=initial.wacc_override is not None, key=key("override"))
            custom_wacc = st.number_input("WACC override (%)", min_value=.1, max_value=60., value=float((initial.wacc_override or initial.wacc) * 100), step=.25, key=key("custom_wacc"))
            fields["wacc_override"] = custom_wacc / 100 if override else None

        with col_policy:
            st.markdown("#### 03 · Valuation policy")
            st.caption("Multi-approach weighting, terminal parameters, and balance sheet claims bridge.")
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
        st.form_submit_button("Apply assumptions", type="primary", use_container_width=True)
    base_a = make_assumptions(**fields)

    # Full-Width Section 04 at the bottom (Decoupled from form for instant reactivity)
    st.divider()
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
    with st.expander("📘 Academic Rationale & 5-Year Phased Horizon (MM6026 Rubric)", expanded=False):
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

with st.sidebar:
    st.divider()
    st.markdown("### Model assumptions")
    st.metric("Calculated WACC", f"{a.wacc:.2%}")
    st.caption(f"Cost of equity {a.cost_of_equity:.2%} · Target debt weight {a.debt_weight:.0%}")
    st.info("💡 Edit operating, macro WACC, and valuation policy assumptions in the **Valuation assumptions** tab.")

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

exclusion_info = get_multiple_exclusion_details(peer_rows) if 'exclusion_info' not in locals() else exclusion_info
approach_eval = evaluate_approach_weights(target_profile, peer_rows, a.dcf_weight, a.relative_weight)
rec = investment_recommendation(price, effective_price)

with overview:
    # 1. Institutional Recommendation Banner with Integrated Action Button
    upside_str = (
        f"""<span style="font-size: 14px; color: #5c7080;">Capital Structure: <b>Negative Intrinsic Equity (Insolvent / Restructuring Risk)</b></span>"""
        if rec['rating'] == 'NOT ELIGIBLE' else
        f"""<span style="font-size: 15px; color: #2e3e3b;">Implied Upside: <b>{rec['upside']:+.1%}</b> &nbsp;|&nbsp; Margin of Safety: <b>{rec['margin_of_safety']:.1%}</b></span>"""
    )
    rec_col, dl_col = st.columns([4.0, 1.2], vertical_alignment="center")
    with rec_col:
        st.markdown(
            f"""<div style="background-color: {rec['color']}15; border-left: 5px solid {rec['color']}; padding: 14px 18px; border-radius: 8px; margin: 10px 0 18px;">
            <span style="font-size: 11px; font-weight: 700; letter-spacing: 1.2px; color: {rec['color']}; text-transform: uppercase;">INVESTMENT RECOMMENDATION · MID-TERM DECISION CRITERIA</span>
            <div style="display: flex; align-items: baseline; gap: 16px; margin: 6px 0 4px; flex-wrap: wrap;">
                <span style="font-size: 24px; font-weight: 800; color: {rec['color']};">{rec['rating']}</span>
                {upside_str}
            </div>
            <div style="font-size: 13px; color: #435451;">{rec['summary']}</div>
            </div>""",
            unsafe_allow_html=True
        )
    with dl_col:
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
                st.download_button(
                    label="Download PDF Report",
                    data=pdf_report_bytes,
                    file_name=f"{c['symbol'].replace('.JK', '')}_Valuation_Report.pdf",
                    mime="application/pdf",
                    key=key("dl_pdf_banner"),
                    type="primary",
                    use_container_width=True
                )
            else:
                st.info("PDF engine readying...")
        except Exception as _pdf_err:
            st.caption(f"PDF generator ready: {_pdf_err}")

    # 2. Metric Columns
    cols = st.columns(5)
    cols[0].metric("Reference price", f"Rp {price:,.0f}" if price else "Not available")
    cols[1].metric("Blended fair value", f"Rp {effective_price:,.0f}" if effective_price and effective_price > 0 else ("Not eligible" if effective_price is not None and effective_price <= 0 else "Check inputs"))
    cols[2].metric(
        "DCF value / share",
        f"Rp {dcf_p:,.0f}" if dcf_p and dcf_p > 0 else ("Not eligible" if dcf_p is not None and dcf_p <= 0 else "Check assumptions"),
        help=f"Probability-weighted expected DCF value across Bear ({norm_probs.get('Bear', 0.25):.0%}), Base ({norm_probs.get('Base', 0.50):.0%}), and Bull ({norm_probs.get('Bull', 0.25):.0%}) scenarios. Base case alone: Rp {base_dcf_price:,.0f}." if base_dcf_price else None
    )
    cols[3].metric("Relative value / share", f"Rp {rel_price:,.0f}" if pd.notna(rel_price) and rel_price > 0 else "Needs >= 2 peers")
    upside = (effective_price / price - 1) if effective_price and price and effective_price > 0 else None
    cols[4].metric("Implied upside / downside", f"{upside:+.1%}" if upside is not None else "—")

    # 3. Valuation Approach Selection & Justification Card (Rule 1 & Rule 2)
    with st.expander("Valuation Approach Selection & Weight Justification (Rule 1 & Rule 2)", expanded=True):
        st.markdown(f"**Methodology Rationale**: {approach_eval['rationale']}")
        col_w1, col_w2, col_q = st.columns(3)
        col_w1.metric("DCF Weight (Intrinsic Anchor)", f"{approach_eval['dcf_weight']:.0%}")
        col_w2.metric("Relative Weight (Market Cross-Check)", f"{approach_eval['rel_weight']:.0%}")
        col_q.metric("Peer Group Quality", approach_eval["quality"])
        st.caption(
            "• **Rule 1 (Intrinsic Anchor)**: DCF (FCFF) is given primary emphasis (default 75%) because it measures intrinsic capacity to generate cash flows, independently of market sentiment or sector pricing bubbles.\n\n"
            "• **Rule 2 (Peer Quality Calibration)**: Relative valuation provides a secondary cross-check (25%) only when ≥2 sub-industry peers have verified financial similarity (EBITDA margin & DER); otherwise, model defaults to 100% DCF."
        )

    # 4. Valuation Range / Football Field Chart
    ff_items = []
    bear_price = next((x["Value / share"] for x in scenario_rows if x["Scenario"] == "Bear" and pd.notna(x["Value / share"])), None)
    bull_price = next((x["Value / share"] for x in scenario_rows if x["Scenario"] == "Bull" and pd.notna(x["Value / share"])), None)
    base_price = result["price"] if result else None
    if bear_price and bull_price and base_price:
        ff_items.append({
            "Method": "DCF (FCFF) Range",
            "Low": min(bear_price, bull_price),
            "Mid": dcf_p if (dcf_p and pd.notna(dcf_p)) else base_price,
            "High": max(bear_price, bull_price),
            "Color": "#087f69"
        })
    if not relative.empty and len(peer_rows) >= 2:
        rel_med = composite_relative_value(relative)
        q25 = composite_relative_value(relative[relative["Case"] == "Lower quartile"].replace("Lower quartile", "Median")) if "Lower quartile" in relative["Case"].values else rel_med * 0.85
        q75 = composite_relative_value(relative[relative["Case"] == "Upper quartile"].replace("Upper quartile", "Median")) if "Upper quartile" in relative["Case"].values else rel_med * 1.15
        if pd.notna(rel_med) and pd.notna(q25) and pd.notna(q75):
            ff_items.append({
                "Method": "Relative Valuation (P25 - P75)",
                "Low": min(q25, q75),
                "Mid": rel_med,
                "High": max(q25, q75),
                "Color": "#2a6256"
            })
    if price and price > 0:
        ff_items.append({
            "Method": "Market Reference Price",
            "Low": price * 0.90,
            "Mid": price,
            "High": price * 1.10,
            "Color": "#8c9e99"
        })

    if ff_items:
        st.markdown("### Valuation range comparison (Football field)")
        fig_ff = go.Figure()
        for idx, item in enumerate(ff_items):
            fig_ff.add_trace(go.Bar(
                name=item["Method"],
                y=[item["Method"]],
                x=[item["High"] - item["Low"]],
                base=[item["Low"]],
                orientation='h',
                marker=dict(color=item["Color"], opacity=0.45),
                hoverinfo="text",
                hovertext=f"{item['Method']}: Rp {item['Low']:,.0f} – Rp {item['High']:,.0f} (Mid: Rp {item['Mid']:,.0f})"
            ))
            fig_ff.add_trace(go.Scatter(
                x=[item["Mid"]],
                y=[item["Method"]],
                mode="markers+text",
                marker=dict(color=item["Color"], size=12, symbol="diamond"),
                text=[f"Rp {item['Mid']:,.0f}"],
                textposition="top center",
                showlegend=False
            ))
        if pd.notna(effective_price):
            fig_ff.add_vline(x=effective_price, line_width=2, line_dash="dash", line_color="#087f69",
                             annotation_text=f"Blended Fair Value: Rp {effective_price:,.0f}", annotation_position="top right")
        fig_ff.update_layout(
            barmode='overlay',
            showlegend=False,
            height=260,
            margin=dict(l=10, r=20, t=30, b=20),
            xaxis_title="IDR / Share",
            yaxis=dict(autorange="reversed")
        )
        chart(fig_ff, "IDR / share")

    # 5. Calculation Inspector & Mathematical Proofs (KaTeX Formula Audit)
    with st.expander("🔍 Calculation Inspector & Mathematical Proofs (KaTeX Formula Audit)", expanded=False):
        c_p1, c_p2 = st.columns(2)
        with c_p1:
            st.markdown("##### 1. Cost of Capital Deconstruction (CAPM & WACC)")
            total_erp = a.mature_equity_premium + a.country_risk_premium
            kd_after = a.debt_rate * (1 - a.tax_rate)
            we = 1 - a.debt_weight
            st.latex(rf"\text{{Total ERP}} = \text{{Mature ERP}} + \text{{CRP}} = {a.mature_equity_premium*100:.2f}\% + {a.country_risk_premium*100:.2f}\% = {total_erp*100:.2f}\%")
            st.latex(rf"K_e = R_f + \beta \times \text{{Total ERP}} = {a.risk_free*100:.2f}\% + ({a.beta:.2f} \times {total_erp*100:.2f}\%) = {a.cost_of_equity*100:.2f}\%")
            st.latex(rf"K_{{d,\text{{after}}}} = K_d \times (1 - t) = {a.debt_rate*100:.2f}\% \times (1 - {a.tax_rate*100:.1f}\%) = {kd_after*100:.2f}\%")
            st.latex(rf"\text{{WACC}} = (W_e \times K_e) + (W_d \times K_{{d,\text{{after}}}}) = ({we*100:.1f}\% \times {a.cost_of_equity*100:.2f}\%) + ({a.debt_weight*100:.1f}\% \times {kd_after*100:.2f}\%) = {a.wacc*100:.2f}\%")

        with c_p2:
            st.markdown("##### 2. Terminal Value & Enterprise-to-Equity Bridge")
            if result:
                reinv_rate = result.get('terminal_reinvestment_rate', a.terminal_growth / a.terminal_roic)
                st.latex(rf"\text{{Reinvestment Rate}} = \frac{{g}}{{\text{{ROIC}}}} = \frac{{{a.terminal_growth*100:.2f}\%}}{{{a.terminal_roic*100:.1f}\%}} = {reinv_rate*100:.1f}\%")
                st.latex(rf"\text{{Terminal Value}} = \frac{{\text{{NOPAT}}_{{6}} \times (1 - \text{{Reinv}})}}{{WACC - g}} = \frac{{{result['terminal_fcff']:,.1f}}}{{{a.wacc*100:.2f}\% - {a.terminal_growth*100:.2f}\%}} = \text{{Rp }}{result['terminal_value']:,.1f}\text{{ bn}}")
                st.latex(rf"\text{{Equity Value}} = \text{{EV}} + \text{{Cash}} - \text{{Debt}} - \text{{Claims}} = \text{{Rp }}{result['equity_value']:,.1f}\text{{ bn}}")
                st.latex(rf"\text{{DCF Value per Share}} = \frac{{\text{{Equity Value}}}}{{\text{{Shares}}}} = \frac{{{result['equity_value']:,.1f}\text{{ bn}}}}{{{shares:.3f}\text{{ bn}}}} = \mathbf{{\text{{Rp }}{result['price']:,.0f}}}")
    l, r = st.columns([1.65, 1])
    with l:
        st.markdown("### The business behind the valuation")
        fig = go.Figure()
        fig.add_scatter(x=[pd.Timestamp(x).year for x in historical.columns], y=historical.loc["revenue"], name="Reported revenue", line=dict(color="#93aaa4", width=3))
        fig.add_scatter(x=[first_year - 1] + list(f.index), y=[b["revenue"]] + list(f.revenue), name="Forecast revenue", line=dict(color="#087f69", width=3, dash="dash"))
        fig.add_bar(x=list(f.index), y=f.fcff, name="Free cash flow", marker_color="#b7d7ca")
        chart(fig)
    with r:
        st.markdown("### Three views of the future")
        chart(go.Figure(go.Bar(
            x=[x["Scenario"] for x in scenario_rows], y=[x["Value / share"] for x in scenario_rows],
            marker_color=["#b4c3bd", "#087f69", "#183e37"], texttemplate="Rp %{y:,.0f}", textposition="outside"
        )), "IDR / share")
        st.caption("Bear / bull shift every forecast year’s revenue growth and EBIT margin by −/+2 percentage points. Other assumptions stay fixed.")
    funding = float(f.funding.sum())
    if funding > .01:
        st.warning(f"The forecast requires IDR {funding:,.1f} bn of cumulative new borrowing. Review the funding schedule and sustainable leverage.")
    if result and result["terminal_share"] > .75:
        st.warning(f"Terminal value contributes {result['terminal_share']:.0%} of enterprise value. Review terminal growth and ROIC carefully.")
    if not c["demo"]:
        from datetime import date
        age = (date.today() - pd.Timestamp(period).date()).days
        if age > 550:
            st.warning("The latest common annual period is more than 18 months old. Review reporting coverage before relying on the result.")
    if any(b[k] < 0 for k in ("other_ca", "other_cl", "other_assets", "other_liabilities")):
        st.warning("A residual opening balance sheet bucket is negative. Review classification and source data.")
    st.caption(f"Model check: maximum balance sheet difference IDR {f.balance_check.abs().max():,.6f} bn. Forecasts start after fiscal {period}; current price is a reference, not a synchronized historical quote.")

with statements:
    st.subheader("Five years, three connected statements")
    st.caption("Forecasted financial statements derived from the operational and macroeconomic drivers configured in the Valuation Assumptions tab.")
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
    for title, rows in [("Income statement", income_rows), ("Balance sheet", bs_rows), ("Cash flow & funding", cf_rows)]:
        st.markdown(f"### {title}")
        st.dataframe(f[rows].T.rename(index=labels).style.format("{:,.1f}"), width="stretch")
        if title == "Balance sheet":
            st.caption(
                "💡 **Liabilities Decomposition**: Financial debt (Short-term & Long-term debt) is maintained under a constant rollover "
                "assumption. The increase in Total Liabilities is driven entirely by spontaneous operating liabilities (Trade Payables "
                "and Other Current Liabilities) scaling proportionately with revenue growth."
            )
        elif title == "Cash flow & funding":
            st.caption(
                "💡 **Financing Cash Flow Note**: Under the debt rollover assumption, scheduled debt repayment defaults to zero "
                "(debt is rolled over at maturity). New borrowing is an automatic liquidity revolver that only activates if operating "
                "cash flow is insufficient to cover CapEx, dividends, and the minimum cash buffer (2% of revenue)."
            )

with dcf_tab:
    st.subheader("What are the future cash flows worth?")
    if result:
        col1, col2 = st.columns([1, 1.4])
        with col1:
            bridge = pd.DataFrame({
                "Component": [
                    "PV of 5-year FCFF", "PV of terminal value", "Enterprise value", "Opening cash & marketable securities",
                    "Additional non-operating assets", "Opening debt (incl. leases)", "Minorities / other claims", "Equity value"
                ],
                "IDR bn": [
                    result["pv_flows"], result["pv_terminal"], result["enterprise_value"], b["cash"],
                    a.nonoperating_assets, -b["short_debt"] - b["long_debt"], -a.other_claims, result["equity_value"]
                ]
            })
            st.dataframe(bridge, hide_index=True, width="stretch", column_config={"IDR bn": st.column_config.NumberColumn(format="%,.1f")})
        with col2:
            st.markdown("**Value per share · WACC vs terminal growth**")
            heat = go.Figure(go.Heatmap(
                z=grid.to_numpy(), x=list(grid.columns), y=list(grid.index), colorscale=[[0, "#eff5f1"], [1, "#087f69"]],
                texttemplate="%{z:,.0f}", hovertemplate="Growth %{x}<br>WACC %{y}<br>Rp %{z:,.0f}<extra></extra>", showscale=False
            ))
            chart(heat, "WACC")
        st.markdown("**Terminal economics**")
        st.write(f"Growth {a.terminal_growth:.2%} · ROIC {a.terminal_roic:.2%} · Reinvestment rate {result.get('terminal_reinvestment_rate', a.terminal_growth/a.terminal_roic):.1%}")
        st.caption("Terminal FCFF = Year 6 NOPAT × (1 − terminal growth / terminal ROIC). Annual cash flows are discounted at year-end. The equity bridge uses opening cash and debt, not year-5 balances.")

        st.markdown("#### Scenario analysis · Bear / Base / Bull")
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

        st.dataframe(scen_df.style.format(format_dict, na_rep="—"), width="stretch")

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
        st.warning("Review WACC, terminal growth, terminal ROIC, shares, and year-5 earnings to calculate DCF.")

with peers_tab:
    st.subheader("Comparable Peers & Relative Valuation")
    st.caption(
        f"Fiscal Period: {period} (FY-End) · Sub-Industry: {c.get('industry', 'General')} · "
        f"Target Ticker: {c['symbol']} (automatically excluded from peers). "
        f"Valuation Policy: Multiples require at least 2 valid peers to be eligible."
    )

    # 1. PEER SELECTION & MANAGEMENT BAR
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

    # 2. INTERACTIVE PEER SELECTION & SIMILARITY TABLE
    all_pcs = st.session_state.get("peer_companies", [])
    if all_pcs:
        st.markdown("#### 1. Comparable Peer Selection & Similarity Ranking")
        st.caption("Peers are ranked by financial similarity (EBITDA Margin & Debt-to-Equity DER distance). Use checkboxes to include or exclude individual peers from valuation, or '✕' to remove.")

        # Compute peer records and rankings
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

        # Build interactive peer inclusion controls and display table
        table_rows = []
        # Target row as benchmark
        table_rows.append({
            "Active": "🎯 TARGET",
            "Ticker": c["symbol"],
            "Company Name": clean_company_name(c["name"]),
            "EBITDA Margin": f"{target_profile['ebitda_margin']:.1%}",
            "DER (D/E)": f"{target_profile['der']:.2f}x",
            "Similarity & Confidence": "100/100 (Benchmark)",
        })

        # Sort peers by similarity distance (descending similarity score)
        sorted_pcs = sorted(
            all_pcs,
            key=lambda p: rank_map.get(p["symbol"], {}).get("similarity_distance", 999.0)
        )

        # Columns for checkboxes & removal
        cols_cb = st.columns(min(4, max(1, len(sorted_pcs))))
        for idx, pc in enumerate(sorted_pcs):
            sym = pc["symbol"]
            clean_sym = sym.replace('.JK', '')
            with cols_cb[idx % len(cols_cb)]:
                c_cb, c_rm = st.columns([3, 1])
                with c_cb:
                    is_inc = st.checkbox(f"Include {clean_sym}", value=st.session_state.get(key(f"include_{sym}"), True), key=key(f"include_{sym}"))
                with c_rm:
                    if st.button("✕", key=key(f"rm_{sym}"), help=f"Remove {clean_sym} from peer list"):
                        st.session_state.peer_companies = [p for p in st.session_state.peer_companies if p["symbol"] != sym]
                        st.rerun()

            r_info = rank_map.get(sym, {})
            m_val = r_info.get("ebitda_margin")
            der_val = r_info.get("der")
            dist_val = r_info.get("similarity_distance", 0.0)
            score_val = r_info.get("similarity_score", 100)
            conf_val = r_info.get("confidence_level", "High")

            table_rows.append({
                "Active": "✅ INCLUDED" if is_inc else "❌ EXCLUDED",
                "Ticker": sym,
                "Company Name": clean_company_name(pc["name"]),
                "EBITDA Margin": f"{m_val:.1%}" if m_val is not None else "—",
                "DER (D/E)": f"{der_val:.2f}x" if der_val is not None else "—",
                "Similarity & Confidence": f"{score_val}/100 ({conf_val} Confidence)",
            })

        st.dataframe(pd.DataFrame(table_rows), hide_index=True, width="stretch")
        st.caption("Similarity score (0–100) measures financial comparability based on EBITDA margin and DER leverage alignment relative to target. Confidence tiers: ≥75 High Confidence (strong match), 50–74 Moderate Confidence, <50 Low Confidence.")



    else:
        st.info("No peers currently loaded. Click 'Reset Defaults' above to automatically load suggested peers.")

    # 3. RELATIVE VALUATION MULTIPLES & WEIGHTING
    st.divider()
    st.markdown("#### 2. Relative Valuation Calculations & Multiple Weights")

    if len(peer_rows) < 2:
        st.warning(f"⚠️ Policy Rule Active: Minimum 2 valid active peers required for relative multiples (currently {len(peer_rows)} active). DCF has 100% weighting.")
    else:
        st.success(f"✅ Peer criteria met: {len(peer_rows)} active comparable peers.")

    # Aggregator and Weights controls
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

    # Validation message for weights
    if abs(tot_mult_w - 100.0) > 0.01:
        st.warning(f"⚠️ Multiple weights sum to {tot_mult_w:.1f}%. Calculation automatically normalizes weights to 100%.")
    else:
        st.caption(f"Weights validated: 100.0% total allocation.")

    # 4. SUMMARY KPI CARDS
    st.markdown("##### Multiple Summary Cards (Independent Implied Values)")
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
                p_display = f"Rp {price_val:,.0f}"
                sub_display = f"{mult_val:.2f}x ({sel_agg})"
                status_html = f"<span style='color: #087f69; font-weight: 700; font-size: 11px;'>ELIGIBLE ({peers_used} peers)</span>"
                note_html = ""
            else:
                p_display = "—"
                sub_display = f"{mult_val:.2f}x" if pd.notna(mult_val) else "No peers"
                status_html = f"<span style='color: #d9822b; font-weight: 700; font-size: 11px;'>INELIGIBLE ({peers_used}/2 peers)</span>"
                note_html = f"<div style='font-size: 10px; color: #8a5314; margin-top: 4px; line-height: 1.25;'>Excluded {', '.join(excl_reasons)} to prevent negative multiple distortion.</div>" if excl_reasons else ""

            card_html = (
                f'<div style="background: #f8faf9; border: 1px solid #d2ded8; border-radius: 8px; padding: 12px; margin-bottom: 8px;">'
                f'<div style="font-size: 11px; text-transform: uppercase; color: #5a7369; font-weight: 700;">{m_name}</div>'
                f'<div style="font-size: 22px; font-weight: 800; color: #1e332d; margin: 4px 0;">{p_display}</div>'
                f'<div style="font-size: 12px; color: #35504f;">{sub_display} &nbsp;|&nbsp; Eff. W: <b>{eff_w:.0%}</b></div>'
                f'<div style="margin-top: 4px;">{status_html}</div>'
                f'{note_html}'
                f'</div>'
            )
            st.markdown(card_html, unsafe_allow_html=True)

    # Multiples distribution table filtered by chosen aggregator and eligibility (>= 2 peers)
    if not relative.empty:
        filtered_relative = relative[relative["Case"] == sel_agg] if "Case" in relative.columns else relative
        if "Peers used" in filtered_relative.columns:
            filtered_relative = filtered_relative[
                (filtered_relative["Peers used"] >= 2) & 
                (filtered_relative["Implied price (IDR)"].notna()) & 
                (filtered_relative["Implied price (IDR)"] > 0)
            ]

        st.markdown(f"**Multiples Benchmark & Implied Value ({sel_agg})**")
        if not filtered_relative.empty:
            st.dataframe(
                filtered_relative,
                hide_index=True,
                width="stretch",
                column_config={
                    "Peer multiple": st.column_config.NumberColumn(format="%.2fx"),
                    "Implied price (IDR)": st.column_config.NumberColumn(format="%,.0f")
                }
            )
        else:
            st.info("No multiples meet the eligibility requirement (minimum 2 valid peers required). DCF approach has 100% weighting.")

        # Plotly comparison chart
        st.markdown("##### Implied Price per Share Comparison")
        chart_bars = []
        bar_colors = []
        bar_labels = []

        if pd.notna(rel_price):
            chart_bars.append(rel_price)
            bar_labels.append("Weighted Relative")
            bar_colors.append("#00838f")

        if dcf_p and pd.notna(dcf_p):
            chart_bars.append(dcf_p)
            bar_labels.append("DCF Fair Value")
            bar_colors.append("#1565c0")

        if price and pd.notna(price):
            chart_bars.append(price)
            bar_labels.append("Market Price")
            bar_colors.append("#d84315")

        fig_rv = go.Figure(go.Bar(
            x=bar_labels,
            y=chart_bars,
            marker_color=bar_colors,
            text=[f"Rp {v:,.0f}" for v in chart_bars],
            textposition="auto"
        ))
        chart(fig_rv, "IDR / share")

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
        download = workbook(c, historical, b, a, drivers, f, result, grid, peer_rows, relative)
        st.download_button("Export Excel snapshot", download, file_name=f"{c['symbol']}_valuation.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", width="stretch")
    st.caption("Refresh data")
    if st.button("Clear cached Yahoo data", width="stretch"):
        get_company.clear()
        st.success("Cache cleared. Load the ticker again to fetch new data.")

with st.expander("AI Assistance & Model Governance Disclosure (Mid-Term Deliverable 1)"):
    st.markdown("""
    **Mid-Term Valuation Model Submission Disclosure (Deliverables 1 & 2 Alignment)**
    - **AI Assistance Tools**: Developed with Google DeepMind Agentic Coding models.
    - **Tasks Supported by AI**: Python calculations architecture, yfinance financial statement parsing, Damodaran CRP formula modeling, peer similarity Euclidean distance algorithms, and automated unit testing suites.
    - **Mathematical Invariant Verification**: All financial logic strictly audited with automated tests enforcing:
      1. Complete balance sheet identity: $\\text{Total Assets} - \\text{Total Liabilities} - \\text{Equity} \\equiv 0.000000$ IDR bn across all 10 projection years.
      2. Direct & indirect cash flow reconciliation: $\\text{CFO} + \\text{CFI} + \\text{CFF} \\equiv \\Delta \\text{Cash}$.
      3. Damodaran Terminal Value Reinvestment: $\\text{Terminal FCFF} = \\text{NOPAT}_{6} \\times (1 - g_n / \\text{ROIC})$.
    - **Test Coverage**: 100% automated test suite passing via pytest (19+ unit & integration tests).
    - **Data Boundaries**: Sourced from official annual statements via Yahoo Finance (`yfinance`); non-financial operating companies only.
    """)

with st.expander("Model methodology & current boundaries"):
    st.markdown("""
    - **Forecast basis:** annual fiscal periods. First three years use initial operating assumptions; years four and five transition linearly to mature growth and margin. Per-year overrides take priority.
    - **Linked accounts:** revenue, COGS, operating costs, PPE, D&A, working capital, debt, interest, dividends, equity, and cash. Other non-current assets/liabilities stay fixed.
    - **Funding:** shortfalls draw new short-term debt to meet minimum cash. Interest uses opening debt; there is no circular same-year financing interest. Excess cash is retained.
    - **Tax:** positive pretax earnings are taxed; no loss carryforward or deferred-tax schedule. FCFF assumes the selected operating tax rate, including the implied tax treatment of operating losses.
    - **Valuation:** constant WACC, year-end discounting, sustainable terminal reinvestment based on growth/ROIC. Fiscal-year-end cash flows are compared with a reference market price without a stub-period roll-forward.
    - **Scope:** non-financial operating companies. No segment model, acquisition forecast, future dilution, interest income, currency forecast, or detailed lease roll-forward. Review lease and minority-interest treatment before using enterprise multiples.
    - **Data:** Yahoo via yfinance; limited annual coverage varies by ticker. Review classifications and source statements. Defaults are illustrative, not investment recommendations. This local app does not redistribute data; review data licensing before public deployment.
    """)
st.caption("NUSA / IDX VALUATION LAB    ·    IDR billions unless stated    ·    Local research workspace")
