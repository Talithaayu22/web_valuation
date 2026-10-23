from dataclasses import asdict, replace
from html import escape
import json
import math
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from valuation.data import CATALOG, BILLION, demo_company, fetch_company, peer_record, ticker_symbol
from valuation.model import Assumptions, BASE_FIELDS, base_check, default_drivers, forecast, dcf, sensitivity, relative_values
from valuation.export import workbook
from valuation import storage

st.set_page_config(page_title="Nusa · IDX Valuation",page_icon="◈",layout="wide")
st.markdown("""<style>
.block-container {padding-top:3.5rem; max-width:1550px; padding-bottom:3rem}
[data-testid="stSidebar"] {border-right:1px solid #dfe8e5}
h1 {font-weight:650!important; letter-spacing:-1.5px!important}
h2,h3 {letter-spacing:-.5px!important}
[data-testid="stMetric"] {background:white; border:1px solid #e0e8e5; border-radius:12px; padding:18px 20px}
[data-testid="stMetricLabel"] {color:#5f7578; font-size:12px; text-transform:uppercase; letter-spacing:.7px}
.eyebrow {color:#087f69; font-size:12px; font-weight:700; letter-spacing:2px; margin-bottom:10px}
.badge {display:inline-block; background:#e3f3ec; color:#087f69; padding:5px 12px; border-radius:20px; font-size:12px}
.hero {padding:23px 28px; background:#173e37; color:white; border-radius:14px; margin:16px 0 24px}
.hero h2 {color:white; margin:0 0 6px; font-size:1.65rem}.hero p {color:#c2dcd3;margin:0}
.small {color:#718481;font-size:12px}
button {border-radius:8px!important}
</style>""",unsafe_allow_html=True)


@st.cache_data(ttl=3600,show_spinner=False)
def get_company(symbol):
    return fetch_company(symbol)


def activate(company, saved=None):
    st.session_state.company = company
    st.session_state.revision = st.session_state.get("revision",0)+1
    st.session_state.saved_inputs = saved or {}
    st.session_state.pop("peer_companies",None)
    st.session_state.pop("peer_errors",None)


def pack_company(c):
    return {k:v for k,v in c.items() if k not in ("historical","raw")}|{
        "historical":c["historical"].to_json(orient="split",date_format="iso"),
        "raw":{name:frame.to_json(orient="split",date_format="iso") for name,frame in c["raw"].items()}}


def unpack_company(c):
    from io import StringIO
    out = dict(c)
    out["historical"] = pd.read_json(StringIO(c["historical"]),orient="split",convert_axes=False)
    out["raw"] = {name:pd.read_json(StringIO(data),orient="split",convert_axes=False) for name,data in c.get("raw",{}).items()}
    return out


def chart(fig, ytitle="IDR billion"):
    fig.update_layout(template="plotly_white",height=350,margin=dict(l=10,r=10,t=25,b=15),
                      font=dict(family="Arial",color="#35504f"),paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(0,0,0,0)",legend=dict(orientation="h",y=1.12,x=0),
                      yaxis_title=ytitle,xaxis_title=None)
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="#e4ebe8",zerolinecolor="#d2ded8")
    st.plotly_chart(fig,width="stretch")


if "company" not in st.session_state:
    activate(demo_company())

with st.sidebar:
    st.markdown("## ◈ Nusa")
    st.caption("THE IDX VALUATION WORKSPACE")
    with st.form("lookup"):
        selected = st.selectbox("Quick select",["Enter a ticker"]+[f"{k} · {v}" for k,v in CATALOG.items()])
        typed = st.text_input("IDX ticker",placeholder="e.g. TLKM",help="Four-character IDX code. .JK is added automatically.")
        submitted = st.form_submit_button("Load company",type="primary",width="stretch")
    if submitted:
        symbol = typed.strip() or (selected.split(" · ")[0] if selected != "Enter a ticker" else "")
        try:
            with st.spinner("Loading annual financial statements…"):
                activate(get_company(ticker_symbol(symbol)))
        except Exception as exc:
            st.error(f"Could not load company: {exc}")
    if st.button("Explore fictional demo",width="stretch"):
        activate(demo_company())
    with st.expander("Saved analyses"):
        saved_list = storage.list_saved()
        if saved_list:
            choice = st.selectbox("Analysis",saved_list,format_func=lambda r:f"{r[1]} · {r[2][:10]}")
            if st.button("Open saved analysis"):
                payload = storage.load(choice[0])
                activate(unpack_company(payload["company"]),payload)
                st.rerun()
        else:
            st.caption("Save your first analysis below after modelling a company.")

c = st.session_state.company
rev = st.session_state.revision
saved = st.session_state.saved_inputs
key = lambda name:f"{rev}_{name}"

st.markdown('<div class="eyebrow">INDONESIA EQUITY RESEARCH / VALUATION LAB</div>',unsafe_allow_html=True)
head, status = st.columns([4,1])
with head:
    st.title("A clearer view of value.")
    st.caption("Connect the statements. Test your assumptions. Understand the price.")
with status:
    st.markdown(f'<div class="badge">{"ILLUSTRATIVE DEMO" if c["demo"] else escape(c["symbol"]) + " · YAHOO DATA"}</div>',unsafe_allow_html=True)
st.markdown(f'<div class="hero"><h2>{escape(c["name"])}</h2><p>{escape(c["sector"])} &nbsp; / &nbsp; {escape(c["industry"])} &nbsp; / &nbsp; IDR valuation</p></div>',unsafe_allow_html=True)
if c["demo"]:
    st.info("You’re viewing a fictional business with illustrative financials. Load an IDX ticker from the sidebar to use Yahoo data.")
else:
    st.caption(f"Retrieved {c['fetched_at']} · Fiscal-year-end valuation convention · Prices may be delayed")
    if c["sector"] == "Financial Services" or any(x in c["industry"].lower() for x in ("bank","insurance","reit")):
        st.warning("This version models non-financial operating companies. Banks, insurers, and REITs need a dedicated valuation model. Choose another company.")
        st.stop()

overview, statements, dcf_tab, peers_tab, data_tab = st.tabs(["Overview","10-year model","DCF & sensitivity","Relative valuation","Data review"])

with data_tab:
    st.subheader("Start with trustworthy inputs")
    st.caption("Source annual statements are retained. All model money is IDR billion; shares are in billions. Expenses are entered as positive amounts.")
    fx = 1.0
    if c["financial_currency"] != "IDR":
        st.warning(f"Reported financial currency: {c['financial_currency'] or 'unknown'}. Enter and verify an IDR conversion before modelling. A single conversion rate is applied to historical figures for this prototype.")
        fx = st.number_input("IDR per 1 reporting-currency unit",min_value=0.,value=float(saved.get("fx",0)),key=key("fx"),format="%.4f")
    if c["price_currency"] != "IDR":
        st.warning("Market price currency is not verified as IDR. Enter an independently verified IDR price below.")
    historical = c["historical"] * fx
    period = str(historical.columns[-1])
    first_year = pd.Timestamp(period).year+1
    st.markdown(f"**Historical annual data · latest common fiscal period {period}**")
    st.dataframe(historical.rename(index=BASE_FIELDS).style.format("{:,.2f}",na_rep="Missing"),width="stretch")
    source_base = historical.loc[list(BASE_FIELDS),historical.columns[-1]]
    base_values = saved.get("base",source_base.to_dict())
    review = pd.DataFrame({"Account":[BASE_FIELDS[k] for k in BASE_FIELDS],
                           "Reported":[source_base[k] for k in BASE_FIELDS],
                           "Value":[base_values.get(k) for k in BASE_FIELDS],
                           "Source":["Saved/user input" if saved else c["provenance"].get(f"{period}:{k}","Illustrative") for k in BASE_FIELDS]},index=list(BASE_FIELDS))
    st.markdown("**Review and correct opening inputs**")
    edited = st.data_editor(review,disabled=["Account","Reported","Source"],column_config={"Value":st.column_config.NumberColumn("Model input · IDR bn",format="%.3f"),"Reported":st.column_config.NumberColumn("Reported · IDR bn",format="%.3f")},
                            height=450,width="stretch",key=key("base_editor"))
    missing = [k for k in BASE_FIELDS if pd.isna(edited.loc[k,"Value"])]
    accept_missing = False
    if missing:
        st.warning("Missing: " + ", ".join(BASE_FIELDS[k] for k in missing))
        accept_missing = st.checkbox("I reviewed the missing accounts and explicitly assume they are zero",key=key("missing"))
    b = {k:float(edited.loc[k,"Value"]) if pd.notna(edited.loc[k,"Value"]) else 0. for k in BASE_FIELDS}
    if abs(base_check(b)) > .01:
        st.error(f"Opening balance sheet difference: IDR {base_check(b):,.2f} bn. Correct the input accounts; the app will not insert a balancing plug.")
    col1,col2 = st.columns(2)
    with col1:
        shares = st.number_input("Current / diluted shares outstanding (billions)",min_value=0.,value=float(saved.get("shares",(c["shares"] or 0)/BILLION)),key=key("shares"),format="%.6f")
    with col2:
        price = st.number_input("Reference market price (IDR/share)",min_value=0.,value=float(saved.get("price",c["price"] or 0)),key=key("price"))
    st.caption("Current shares are a no-future-dilution assumption. Override with diluted shares if needed. Other current assets/liabilities are treated as operating; reclassify them when reviewing inputs.")
    for name,raw in c["raw"].items():
        with st.expander(f"Raw source · {name} · {c['financial_currency'] or 'currency unverified'} units"):
            st.dataframe(raw,width="stretch")

if fx <= 0 or (missing and not accept_missing):
    with overview:
        st.warning("Open Data review and complete the missing inputs or currency conversion to unlock the forecast.")
    st.stop()

def inferred_assumptions():
    a = Assumptions()
    r = b["revenue"]
    if r > 0:
        a.ebit_margin = max(-.2,min(.5,(r-b["cogs"]-b["opex"]-b["da"])/r))
        a.mature_margin = a.ebit_margin
        a.gross_margin = max(.05,min(.95,1-b["cogs"]/r))
        a.ar_days = max(0,min(365,b["ar"]/r*365))
        a.inventory_days = max(0,min(365,b["inventory"]/b["cogs"]*365)) if b["cogs"] > 0 else 0
        a.ap_days = max(0,min(365,b["ap"]/b["cogs"]*365)) if b["cogs"] > 0 else 0
        a.other_ca_pct = max(0,min(.5,b["other_ca"]/r))
        a.other_cl_pct = max(0,min(.5,b["other_cl"]/r))
        reported_capex = historical.iloc[:,-1].get("capex")
        if pd.notna(reported_capex):
            a.capex_pct = max(0,min(1,float(reported_capex)/r))
    if b["ppe"] > 0:
        a.depreciation_rate = max(0,min(1,b["da"]/b["ppe"]))
    minority = historical.iloc[:,-1].get("minority_interest")
    if pd.notna(minority):
        a.other_claims = max(0,float(minority))
    if c.get("beta") is not None and 0 <= c["beta"] <= 4:
        a.beta = c["beta"]
    return a

initial = Assumptions(**saved["assumptions"]) if saved.get("assumptions") else inferred_assumptions()
with st.sidebar:
    st.divider()
    st.markdown("### Model assumptions")
    st.caption("Operating ratios start from the latest annual data where available. Growth, discount-rate, and terminal assumptions are editable examples. Click Apply to update.")
    with st.form(key("assumptions")):
        fields = {}
        def pct(label,field,lo=0.,hi=100.):
            fields[field] = st.number_input(label,min_value=float(lo),max_value=float(hi),value=float(getattr(initial,field)*100),step=.5,key=key(field))/100
        with st.expander("Growth & profitability",expanded=True):
            pct("Growth · years 1–5 (%)","growth",-50,100)
            pct("Growth · year 10 (%)","mature_growth",-50,50)
            pct("EBIT margin · years 1–5 (%)","ebit_margin",-50,80)
            pct("EBIT margin · year 10 (%)","mature_margin",-50,80)
            pct("Gross margin (%)","gross_margin",1,100)
            pct("Tax rate (%)","tax_rate",0,60)
        with st.expander("Investment & working capital"):
            pct("Capex / revenue (%)","capex_pct",0,100)
            pct("D&A / opening fixed assets (%)","depreciation_rate",0,100)
            for label,field in [("Receivable days","ar_days"),("Inventory days","inventory_days"),("Payable days","ap_days")]:
                fields[field] = st.number_input(label,min_value=0.,max_value=730.,value=float(getattr(initial,field)),key=key(field))
            pct("Other operating CA / sales (%)","other_ca_pct",0,100)
            pct("Other operating CL / sales (%)","other_cl_pct",0,100)
        with st.expander("Debt, cash & distributions"):
            pct("Borrowing cost (%)","debt_rate",0,50)
            fields["annual_repayment"] = st.number_input("Annual debt repayment (IDR bn)",min_value=0.,value=float(initial.annual_repayment),key=key("annual_repayment"))
            pct("Dividend payout (%)","dividend_payout",0,100)
            pct("Minimum cash / revenue (%)","minimum_cash_pct",0,100)
        with st.expander("Discount rate & terminal value",expanded=True):
            pct("IDR risk-free rate (%)","risk_free",0,30)
            fields["beta"] = st.number_input("Levered beta",min_value=0.,max_value=4.,value=float(initial.beta),step=.05,key=key("beta"))
            pct("Total equity risk premium (%)","equity_premium",0,30)
            st.caption("Include any country-risk adjustment in this total; do not add it twice.")
            pct("Target debt / capital (%)","debt_weight",0,95)
            override = st.checkbox("Override calculated WACC",value=initial.wacc_override is not None,key=key("override"))
            custom_wacc = st.number_input("WACC override (%)",min_value=.1,max_value=60.,value=float((initial.wacc_override or initial.wacc)*100),step=.25,key=key("custom_wacc"))
            fields["wacc_override"] = custom_wacc/100 if override else None
            pct("Terminal growth (%)","terminal_growth",0,15)
            pct("Terminal return on invested capital (%)","terminal_roic",.1,100)
            fields["other_claims"] = st.number_input("Minorities / other equity claims (IDR bn)",min_value=0.,value=float(initial.other_claims),key=key("claims"))
            st.caption("Starts with reported minority book value where available; review valuation and add other claims.")
            fields["nonoperating_assets"] = st.number_input("Additional non-operating assets (IDR bn)",min_value=0.,value=float(initial.nonoperating_assets),key=key("nonop"))
        st.form_submit_button("Apply assumptions",type="primary",width="stretch")
    a = Assumptions(**fields)
    st.metric("Calculated WACC",f"{a.wacc:.2%}")
    st.caption(f"Cost of equity {a.cost_of_equity:.2%} · Target debt weight {a.debt_weight:.0%}")

with statements:
    st.subheader("Ten years, three connected statements")
    st.caption("Edit the annual drivers below. Values use percent points: enter 8 for 8%. Reset restores the sidebar assumptions.")
    if st.button("Reset annual overrides",key=key("reset")):
        st.session_state[key("driver_version")] = st.session_state.get(key("driver_version"),0)+1
        st.session_state[key("ignore_saved_drivers")] = True
    # A new defaults signature resets the annual editor when global drivers change.
    driver_defaults = default_drivers(a,first_year)
    signature = str((a.growth,a.mature_growth,a.ebit_margin,a.mature_margin,a.capex_pct))
    saved_drivers = saved.get("drivers") if not st.session_state.get(key("ignore_saved_drivers")) else None
    if saved_drivers and signature == str((initial.growth,initial.mature_growth,initial.ebit_margin,initial.mature_margin,initial.capex_pct)):
        driver_defaults = pd.DataFrame(saved_drivers)
    drivers = st.data_editor(driver_defaults,hide_index=True,disabled=["Year"],width="stretch",height=390,
                             key=key(f"drivers_{signature}_{st.session_state.get(key('driver_version'),0)}"))

try:
    f = forecast(b,a,first_year,drivers)
except ValueError as exc:
    with overview:
        st.error(str(exc))
    st.stop()

try:
    result = dcf(f,b,a,shares)
    grid = sensitivity(f,b,a,shares)
except ValueError as exc:
    result = None
    grid = pd.DataFrame()
    with overview:
        st.warning(f"DCF unavailable: {exc}. You can still review the financial forecast.")

scenario_rows = []
for label,shift in [("Bear",-.02),("Base",0),("Bull",.02)]:
    sd = drivers.copy()
    sd["Growth %"] += shift*100
    sd["EBIT margin %"] += shift*100
    try:
        sf = forecast(b,a,first_year,sd)
        sr = dcf(sf,b,a,shares)
        scenario_rows.append({"Scenario":label,"Value / share":sr["price"],"Year 10 revenue":sf.iloc[-1].revenue,"Year 10 EBIT":sf.iloc[-1].ebit,"WACC":a.wacc})
    except ValueError:
        scenario_rows.append({"Scenario":label,"Value / share":float("nan"),"Year 10 revenue":float("nan"),"Year 10 EBIT":float("nan"),"WACC":a.wacc})

with overview:
    cols = st.columns(4)
    cols[0].metric("Reference price",f"Rp {price:,.0f}" if price else "Not available")
    cols[1].metric("DCF value / share",f"Rp {result['price']:,.0f}" if result else "Check assumptions")
    upside = result["price"]/price-1 if result and price else None
    cols[2].metric("Implied upside / downside",f"{upside:+.1%}" if upside is not None else "—")
    cols[3].metric("Discount rate",f"{a.wacc:.2%}")
    l,r = st.columns([1.65,1])
    with l:
        st.markdown("### The business behind the valuation")
        fig = go.Figure()
        fig.add_scatter(x=[pd.Timestamp(x).year for x in historical.columns],y=historical.loc["revenue"],name="Reported revenue",line=dict(color="#93aaa4",width=3))
        fig.add_scatter(x=[first_year-1]+list(f.index),y=[b["revenue"]]+list(f.revenue),name="Forecast revenue",line=dict(color="#087f69",width=3,dash="dash"))
        fig.add_bar(x=list(f.index),y=f.fcff,name="Free cash flow",marker_color="#b7d7ca")
        chart(fig)
    with r:
        st.markdown("### Three views of the future")
        chart(go.Figure(go.Bar(x=[x["Scenario"] for x in scenario_rows],y=[x["Value / share"] for x in scenario_rows],
                              marker_color=["#b4c3bd","#087f69","#183e37"],texttemplate="Rp %{y:,.0f}",textposition="outside")),"IDR / share")
        st.caption("Bear / bull shift every forecast year’s revenue growth and EBIT margin by −/+2 percentage points. Other assumptions stay fixed.")
    funding = float(f.funding.sum())
    if funding > .01:
        st.warning(f"The forecast requires IDR {funding:,.1f} bn of cumulative new borrowing. Review the funding schedule and sustainable leverage.")
    if result and result["terminal_share"] > .75:
        st.warning(f"Terminal value contributes {result['terminal_share']:.0%} of enterprise value. Review terminal growth and ROIC carefully.")
    if not c["demo"]:
        from datetime import date
        age = (date.today()-pd.Timestamp(period).date()).days
        if age > 550:
            st.warning("The latest common annual period is more than 18 months old. Review reporting coverage before relying on the result.")
    if any(b[k] < 0 for k in ("other_ca","other_cl","other_assets","other_liabilities")):
        st.warning("A residual opening balance sheet bucket is negative. Review classification and source data.")
    st.caption(f"Model check: maximum balance sheet difference IDR {f.balance_check.abs().max():,.6f} bn. Forecasts start after fiscal {period}; current price is a reference, not a synchronized historical quote.")

with statements:
    income_rows = ["revenue","cogs","opex","da","ebitda","ebit","interest","tax","net_income"]
    bs_rows = ["cash","ar","inventory","other_ca","ppe","other_assets","assets","ap","other_cl","short_debt","long_debt","other_liabilities","liabilities","equity","balance_check"]
    cf_rows = ["net_income","da","delta_nwc","cfo","capex","cfi","funding","repayment","dividends","cff","cash_change","cash","fcff"]
    labels = BASE_FIELDS|{"ebitda":"EBITDA","ebit":"EBIT","assets":"Total assets","liabilities":"Total liabilities","balance_check":"Balance check",
                         "delta_nwc":"Increase in operating working capital","cfo":"Operating cash flow","capex":"Capital expenditure (outflow)","cfi":"Investing cash flow",
                         "funding":"New borrowing / funding need","repayment":"Debt repayment (outflow)","dividends":"Dividends (outflow)",
                         "cff":"Financing cash flow","cash_change":"Net cash movement","fcff":"Free cash flow to firm"}
    for title,rows in [("Income statement",income_rows),("Balance sheet",bs_rows),("Cash flow & funding",cf_rows)]:
        st.markdown(f"### {title}")
        st.dataframe(f[rows].T.rename(index=labels).style.format("{:,.1f}"),width="stretch")

with dcf_tab:
    st.subheader("What are the future cash flows worth?")
    if result:
        col1,col2 = st.columns([1,1.4])
        with col1:
            bridge = pd.DataFrame({"Component":["PV of 10-year FCFF","PV of terminal value","Enterprise value","Opening cash","Additional non-operating assets","Opening debt","Minorities / other claims","Equity value"],
                                   "IDR bn":[result["pv_flows"],result["pv_terminal"],result["enterprise_value"],b["cash"],a.nonoperating_assets,-b["short_debt"]-b["long_debt"],-a.other_claims,result["equity_value"]]})
            st.dataframe(bridge,hide_index=True,width="stretch",column_config={"IDR bn":st.column_config.NumberColumn(format="%,.1f")})
        with col2:
            st.markdown("**Value per share · WACC vs terminal growth**")
            heat = go.Figure(go.Heatmap(z=grid.to_numpy(),x=list(grid.columns),y=list(grid.index),colorscale=[[0,"#eff5f1"],[1,"#087f69"]],
                                        texttemplate="%{z:,.0f}",hovertemplate="Growth %{x}<br>WACC %{y}<br>Rp %{z:,.0f}<extra></extra>",showscale=False))
            chart(heat,"WACC")
        st.markdown("**Terminal economics**")
        st.write(f"Growth {a.terminal_growth:.2%} · ROIC {a.terminal_roic:.2%} · Reinvestment rate {a.terminal_growth/a.terminal_roic:.1%}")
        st.caption("Terminal FCFF = Year 11 NOPAT × (1 − terminal growth / terminal ROIC). Annual cash flows are discounted at year-end. The equity bridge uses opening cash and debt, not year-10 balances.")
        st.dataframe(pd.DataFrame(scenario_rows).set_index("Scenario").style.format("{:,.2f}"),width="stretch")
    else:
        st.warning("Review WACC, terminal growth, terminal ROIC, shares, and year-10 earnings to calculate DCF.")

peer_rows = []
relative = pd.DataFrame()
with peers_tab:
    st.subheader("Value in the company of peers")
    st.caption(f"Annual fiscal-period basis: {period}. All peers must match this exact period. Multiples are calculated from statements and reference prices; forward and TTM figures are not mixed.")
    peer_text = st.text_input("Peer IDX tickers, separated by commas",placeholder="ICBP, INDF, MYOR",key=key("peer_text"))
    if st.button("Fetch peer financials",type="primary",key=key("fetch_peers")):
        companies,errors = [],[]
        with st.spinner("Loading peer statements…"):
            for value in list(dict.fromkeys(peer_text.split(",")))[:8]:
                if not value.strip():
                    continue
                try:
                    symbol = ticker_symbol(value)
                    if symbol == c["symbol"]:
                        raise ValueError("Target company cannot be its own peer.")
                    pc = get_company(symbol)
                    if pc["sector"] == "Financial Services":
                        raise ValueError("Financial-sector companies are not comparable in this operating-company model.")
                    companies.append(pc)
                except Exception as exc:
                    errors.append(f"{value.strip()}: {exc}")
        st.session_state.peer_companies = companies
        st.session_state.peer_errors = errors
    for error in st.session_state.get("peer_errors",[]):
        st.warning(error)
    for pc in st.session_state.get("peer_companies",[]):
        with st.expander(f"{pc['symbol']} · {pc['name']}",expanded=True):
            if not st.checkbox("Include in comparison",value=True,key=key(f"include_{pc['symbol']}")):
                continue
            st.caption(f"{pc['sector']} / {pc['industry']} · Financial currency {pc['financial_currency']} · Retrieved {pc['fetched_at']}")
            pfx = 1.
            if pc["financial_currency"] != "IDR":
                pfx = st.number_input("IDR per reporting currency unit",min_value=0.,value=0.,key=key(f"fx_{pc['symbol']}"))
            claims = st.number_input("Net EV adjustment: minorities + other claims − non-operating assets (IDR bn)",value=0.,key=key(f"claims_{pc['symbol']}"))
            try:
                if pfx <= 0:
                    raise ValueError("Verify the currency conversion to include this peer.")
                peer_rows.append(peer_record(pc,period,pfx,claims))
            except ValueError as exc:
                st.warning(str(exc))
    # A saved peer snapshot can be reviewed offline without silently refetching it.
    if not st.session_state.get("peer_companies") and saved.get("peers"):
        peer_rows = saved["peers"]
        st.info("Using the peer snapshot from this saved analysis. Fetch peers above to replace it with fresh data.")
    if peer_rows:
        st.dataframe(pd.DataFrame(peer_rows),hide_index=True,width="stretch")
        target = dict(revenue=b["revenue"],ebit=b["revenue"]-b["cogs"]-b["opex"]-b["da"],
                      ebitda=b["revenue"]-b["cogs"]-b["opex"],net_income=b["net_income"])
        if shares > 0:
            relative = relative_values(peer_rows,target,b["cash"],b["short_debt"]+b["long_debt"],shares,a.other_claims,a.nonoperating_assets)
            st.dataframe(relative,hide_index=True,width="stretch",column_config={"Peer multiple":st.column_config.NumberColumn(format="%.2fx"),"Implied price (IDR)":st.column_config.NumberColumn(format="%,.0f")})
            med = relative[relative.Case == "Median"]
            chart(go.Figure(go.Bar(x=med.Multiple,y=med["Implied price (IDR)"],marker_color="#087f69")),"IDR / share")
            st.caption("Non-positive EV, market capitalization, or denominators are excluded per multiple. Quartiles from a small peer group are descriptive; assess growth, margin, leverage, accounting, and business mix before interpreting them.")
    else:
        st.info("Choose comparable IDX businesses to calculate EV/Revenue, EV/EBITDA, EV/EBIT, and P/E ranges. Peer data is fetched only when requested.")

with st.sidebar:
    st.divider()
    st.markdown("### Keep your work")
    analysis_name = st.text_input("Analysis name",value=f"{c['symbol']} · Base case",key=key("analysis_name"))
    payload = dict(company=pack_company(c),base=b,assumptions=asdict(a),drivers=drivers.to_dict(orient="list"),shares=shares,price=price,fx=fx,peers=peer_rows)
    if st.button("Save analysis",width="stretch"):
        try:
            storage.save(analysis_name,payload)
            st.success("Saved on this PC. Open it under Saved analyses.")
        except (ValueError,TypeError) as exc:
            st.error(f"Could not save: {exc}")
    if result:
        download = workbook(c,historical,b,a,drivers,f,result,grid,peer_rows,relative)
        st.download_button("Export Excel snapshot",download,file_name=f"{c['symbol']}_valuation.xlsx",mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",width="stretch")
    st.caption("Refresh data")
    if st.button("Clear cached Yahoo data",width="stretch"):
        get_company.clear()
        st.success("Cache cleared. Load the ticker again to fetch new data.")

with st.expander("Model methodology & current boundaries"):
    st.markdown("""
    - **Forecast basis:** annual fiscal periods. First five years use the operating assumptions; years six to ten transition linearly to mature growth and margin. Per-year overrides take priority.
    - **Linked accounts:** revenue, COGS, operating costs, PPE, D&A, working capital, debt, interest, dividends, equity, and cash. Other non-current assets/liabilities stay fixed.
    - **Funding:** shortfalls draw new short-term debt to meet minimum cash. Interest uses opening debt; there is no circular same-year financing interest. Excess cash is retained.
    - **Tax:** positive pretax earnings are taxed; no loss carryforward or deferred-tax schedule. FCFF assumes the selected operating tax rate, including the implied tax treatment of operating losses.
    - **Valuation:** constant WACC, year-end discounting, sustainable terminal reinvestment based on growth/ROIC. Fiscal-year-end cash flows are compared with a reference market price without a stub-period roll-forward.
    - **Scope:** non-financial operating companies. No segment model, acquisition forecast, future dilution, interest income, currency forecast, or detailed lease roll-forward. Review lease and minority-interest treatment before using enterprise multiples.
    - **Data:** Yahoo via yfinance; limited annual coverage varies by ticker. Review classifications and source statements. Defaults are illustrative, not investment recommendations. This local app does not redistribute data; review data licensing before public deployment.
    """)
st.caption("NUSA / IDX VALUATION LAB    ·    IDR billions unless stated    ·    Local research workspace")
