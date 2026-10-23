"""Yahoo adapter. Missing source values remain missing until user review."""
from datetime import datetime, timezone
from pathlib import Path
import math
import re
import pandas as pd
import yfinance as yf
from .model import BASE_FIELDS

BILLION = 1e9
CATALOG = {
    "TLKM": "Telkom Indonesia", "ASII": "Astra International", "ICBP": "Indofood CBP",
    "INDF": "Indofood Sukses Makmur", "UNVR": "Unilever Indonesia", "KLBF": "Kalbe Farma",
    "MYOR": "Mayora Indah", "SIDO": "Industri Jamu Sido Muncul", "SMGR": "Semen Indonesia",
    "INTP": "Indocement", "UNTR": "United Tractors", "ADRO": "Alamtri Resources Indonesia",
    "PTBA": "Bukit Asam", "ITMG": "Indo Tambangraya Megah", "ANTM": "Aneka Tambang",
    "BBCA": "Bank Central Asia", "BBRI": "Bank Rakyat Indonesia", "BMRI": "Bank Mandiri",
}


def ticker_symbol(value):
    v = value.strip().upper()
    if v.endswith(".JK"):
        v = v[:-3]
    if not re.fullmatch(r"[A-Z0-9]{4}",v):
        raise ValueError("Enter a four-character IDX ticker, for example TLKM or TLKM.JK.")
    return v + ".JK"


def number(value):
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (TypeError,ValueError):
        return None


def pick(frame, period, *names):
    if frame.empty or period not in frame.columns:
        return None
    for name in names:
        if name in frame.index:
            n = number(frame.at[name,period])
            if n is not None:
                return n/BILLION
    return None


def subtract(total, *parts):
    return total-sum(parts) if total is not None and all(p is not None for p in parts) else None


def normalize(income, balance, cashflow):
    records, provenance = {}, {}
    # A common fiscal period is required; never mix different closing dates.
    periods = sorted(set(income.columns) & set(balance.columns) & set(cashflow.columns))
    for period in periods:
        inc = lambda *keys: pick(income,period,*keys)
        bs = lambda *keys: pick(balance,period,*keys)
        cf = lambda *keys: pick(cashflow,period,*keys)
        p = {}
        def put(key,val,source):
            p[key] = val
            provenance[f"{pd.Timestamp(period).date()}:{key}"] = source if val is not None else "Missing — enter or explicitly accept zero"
        put("revenue",inc("TotalRevenue","OperatingRevenue"),"Reported: revenue")
        cogs = inc("CostOfRevenue","ReconciledCostOfRevenue")
        put("cogs",abs(cogs) if cogs is not None else None,"Reported: cost of revenue (positive expense)")
        da = cf("DepreciationAndAmortization","DepreciationAmortizationDepletion")
        if da is None:
            da = inc("ReconciledDepreciation","DepreciationAndAmortizationInIncomeStatement")
        put("da",abs(da) if da is not None else None,"Reported: D&A; used as total operating D&A")
        ebit = inc("OperatingIncome","EBIT")
        # EBITDA - EBIT provides a useful fallback when cash-flow D&A is absent.
        if p["da"] is None:
            put("da",subtract(inc("EBITDA"),ebit),"Calculated: EBITDA less EBIT")
        put("opex",subtract(p["revenue"],p["cogs"],p["da"],ebit),"Calculated: revenue − COGS − D&A − EBIT")
        interest = inc("InterestExpense","InterestExpenseNonOperating")
        put("interest",abs(interest) if interest is not None else None,"Reported: interest expense")
        put("tax",inc("TaxProvision"),"Reported: tax provision")
        put("net_income",inc("NetIncomeCommonStockholders","NetIncome"),"Reported: common-shareholder net income where available")
        put("cash",bs("CashAndCashEquivalents","CashCashEquivalentsAndShortTermInvestments"),"Reported: cash (includes short-term investments if cash unavailable)")
        put("ar",bs("Receivables","AccountsReceivable"),"Reported: receivables")
        put("inventory",bs("Inventory"),"Reported: inventory")
        put("other_ca",subtract(bs("CurrentAssets"),p["cash"],p["ar"],p["inventory"]),"Calculated: current assets less cash, receivables and inventory")
        put("ppe",bs("NetPPE"),"Reported: net PPE")
        put("other_assets",subtract(bs("TotalAssets"),bs("CurrentAssets"),p["ppe"]),"Calculated: assets less current assets and PPE")
        put("ap",bs("AccountsPayable"),"Reported: accounts payable")
        put("short_debt",bs("CurrentDebtAndCapitalLeaseObligation","CurrentDebt"),"Reported: current debt including leases where available")
        long_debt = bs("LongTermDebtAndCapitalLeaseObligation","LongTermDebt")
        put("long_debt",long_debt if long_debt is not None else subtract(bs("TotalDebt"),p["short_debt"]),"Reported/derived: non-current debt")
        put("other_cl",subtract(bs("CurrentLiabilities"),p["ap"],p["short_debt"]),"Calculated: current liabilities less payables and current debt")
        put("other_liabilities",subtract(bs("TotalLiabilitiesNetMinorityInterest"),bs("CurrentLiabilities"),p["long_debt"]),"Calculated: liabilities less current liabilities and long-term debt")
        put("equity",bs("TotalEquityGrossMinorityInterest","StockholdersEquity"),"Reported: total equity; review minority interests separately")
        p["ebit"] = ebit
        p["ebitda"] = ebit+p["da"] if ebit is not None and p["da"] is not None else None
        p["cfo"] = cf("OperatingCashFlow","CashFlowFromContinuingOperatingActivities","CashFlowsfromusedinOperatingActivitiesDirect")
        capex = cf("CapitalExpenditure")
        p["capex"] = abs(capex) if capex is not None else None
        p["minority_interest"] = bs("MinorityInterest")
        if p["minority_interest"] is None:
            p["minority_interest"] = subtract(bs("TotalEquityGrossMinorityInterest"),bs("StockholdersEquity"))
        records[str(pd.Timestamp(period).date())] = p
    frame = pd.DataFrame(records).apply(pd.to_numeric,errors="coerce")
    # Yahoo sometimes returns empty placeholder years shared by every statement.
    frame = frame.loc[:,frame.notna().any(axis=0)]
    return frame, provenance


def fetch_company(symbol):
    symbol = ticker_symbol(symbol)
    cache = Path(__file__).resolve().parents[1]/"data"/"yfinance"
    cache.mkdir(parents=True,exist_ok=True)
    yf.set_tz_cache_location(str(cache))
    t = yf.Ticker(symbol)
    info = t.get_info()
    income = t.get_income_stmt(freq="yearly")
    balance = t.get_balance_sheet(freq="yearly")
    cashflow = t.get_cashflow(freq="yearly")
    if any(x.empty for x in (income,balance,cashflow)):
        raise ValueError(f"Yahoo returned incomplete annual statements for {symbol}. Try again later or use another ticker.")
    historical, provenance = normalize(income,balance,cashflow)
    if historical.empty:
        raise ValueError("No common annual fiscal dates across all three statements.")
    return dict(symbol=symbol,name=info.get("longName",symbol),sector=info.get("sector","Unknown"),
                industry=info.get("industry","Unknown"),financial_currency=info.get("financialCurrency"),
                price_currency=info.get("currency"),price=number(info.get("currentPrice",info.get("regularMarketPrice"))),
                shares=number(info.get("sharesOutstanding")),beta=number(info.get("beta")),
                market_cap=number(info.get("marketCap")),fetched_at=datetime.now(timezone.utc).isoformat(),
                historical=historical,provenance=provenance,
                raw={"Income statement":income,"Balance sheet":balance,"Cash flow":cashflow},demo=False)


def demo_company():
    # Intentionally fictional; never presented as a real IDX security.
    base = dict(revenue=10000.,cogs=6000.,opex=1700.,da=500.,interest=160.,tax=360.8,net_income=1279.2,
                cash=1500.,ar=1200.,inventory=1000.,other_ca=200.,ppe=4500.,other_assets=1600.,
                ap=900.,other_cl=400.,short_debt=300.,long_debt=1700.,other_liabilities=700.,equity=6000.)
    hist = {}
    for year,scale in [(2022,.78),(2023,.85),(2024,.93),(2025,1.)]:
        row = {k:v*scale for k,v in base.items()}
        row.update(ebit=1800*scale,ebitda=2300*scale,cfo=1600*scale,capex=600*scale)
        hist[f"{year}-12-31"] = row
    return dict(symbol="DEMO",name="Nusantara Consumer · Fictional company",sector="Consumer Defensive",
                industry="Illustrative consumer business",financial_currency="IDR",price_currency="IDR",price=1250.,
                shares=8e9,beta=1.,market_cap=10000e9,fetched_at="Illustrative data, not market data",
                historical=pd.DataFrame(hist),provenance={},raw={},demo=True)


def peer_record(company, period, fx, claims=0):
    h = company["historical"]
    if period not in h.columns:
        raise ValueError(f"No matching fiscal period {period}; excluded rather than mixing periods.")
    if company["price_currency"] != "IDR":
        raise ValueError("Price currency is not verified as IDR.")
    price, shares = company["price"],company["shares"]
    if not price or not shares:
        raise ValueError("Market price or shares unavailable.")
    p = h[period]
    if any(pd.isna(p.get(k)) for k in ("cash","short_debt","long_debt")):
        raise ValueError("Cash or debt unavailable; cannot calculate a comparable EV.")
    market_cap = price*shares/BILLION
    return dict(ticker=company["symbol"],name=company["name"],period=period,market_cap=market_cap,
                ev=market_cap + (p.short_debt+p.long_debt-p.cash)*fx + claims,
                **{k:None if pd.isna(p.get(k)) else float(p[k])*fx for k in ("revenue","ebitda","ebit","net_income")})
