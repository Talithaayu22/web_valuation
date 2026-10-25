"""Yahoo adapter and financial dataset normalizer for IDX issuers.
Aligned with Aswath Damodaran's DCF and Relative Valuation data standards.
"""
from datetime import datetime, timezone
from pathlib import Path
import functools
import math
import re
import pandas as pd
import yfinance as yf
from .model import BASE_FIELDS


try:
    from curl_cffi import requests as curl_requests

    class DoHSession(curl_requests.Session):
        """curl_cffi Session that routes DNS queries over HTTPS (port 443)
        to bypass ISP UDP port 53 DNS throttling / RCODE_SERVER_FAILURE.
        """
        def request(self, method, url, **kwargs):
            if "doh_url" not in kwargs or not kwargs["doh_url"]:
                kwargs["doh_url"] = "https://8.8.8.8/dns-query"
            try:
                return super().request(method, url, **kwargs)
            except Exception:
                kwargs["doh_url"] = "https://1.1.1.1/dns-query"
                return super().request(method, url, **kwargs)

    def get_doh_session():
        return DoHSession(impersonate="chrome")

except ImportError:
    def get_doh_session():
        return None

__all__ = [
    "CATALOG", "BILLION", "demo_company", "demo_peers", "fetch_company", 
    "peer_record", "ticker_symbol", "get_default_peers_for_ticker", 
    "get_or_fetch_peers", "rank_peers_similarity", "get_doh_session", "normalize",
    "load_idx_company_registry", "get_company_idx_metadata",
]

BILLION = 1e9


@functools.lru_cache(maxsize=1)
def _load_idx_registry_data():
    excel_path = Path(__file__).resolve().parent.parent / "book" / "Company LIsted on IDX.xlsx"
    if not excel_path.exists():
        return {}, {}, {}, {}
    try:
        df = pd.read_excel(excel_path, header=3)
        df = df.dropna(subset=["Code"])
        df["Code"] = df["Code"].astype(str).str.strip().str.upper()
        df["Sector"] = df["Sector"].astype(str).str.strip()
        df["Sub Industry"] = df["Sub Industry"].astype(str).str.strip()
        df["Stock Name"] = df["Stock Name"].astype(str).str.strip()
        if "Sub Industry Code" in df.columns:
            df["Sub Industry Code"] = df["Sub Industry Code"].astype(str).str.strip().str.upper()
        else:
            df["Sub Industry Code"] = ""

        ticker_map = {}
        sub_ind_map = {}
        sector_map = {}
        group_map = {}

        for _, row in df.iterrows():
            code = row["Code"]
            sec = row["Sector"]
            sub = row["Sub Industry"]
            name = row["Stock Name"]
            sub_code = str(row.get("Sub Industry Code", "") or "").strip().upper()
            group_code = sub_code[:2] if len(sub_code) >= 2 else ""

            ticker_map[code] = {
                "code": code,
                "name": name,
                "sector": sec,
                "sub_industry": sub,
                "sub_industry_code": sub_code,
                "group_code": group_code,
            }
            if sub not in sub_ind_map:
                sub_ind_map[sub] = []
            sub_ind_map[sub].append(code)

            if group_code:
                if group_code not in group_map:
                    group_map[group_code] = []
                group_map[group_code].append(code)

            if sec not in sector_map:
                sector_map[sec] = []
            sector_map[sec].append(code)

        return ticker_map, sub_ind_map, sector_map, group_map
    except Exception:
        return {}, {}, {}, {}


def load_idx_company_registry(include_groups=False):
    """Loads and caches official IDX listed company metadata from the repository Excel file:
    'book/Company LIsted on IDX.xlsx'.
    Only Sector, Sub-Industry, Sub-Industry Code, and official Stock Name are sourced here.
    Financial data continues to be retrieved from yfinance.
    """
    t_map, s_map, sec_map, g_map = _load_idx_registry_data()
    if include_groups:
        return t_map, s_map, sec_map, g_map
    return t_map, s_map, sec_map


def get_company_idx_metadata(symbol):
    """Retrieves official IDX listed company metadata for a ticker from the Excel registry."""
    clean = symbol.replace(".JK", "").strip().upper()
    ticker_map, _, _ = load_idx_company_registry()
    return ticker_map.get(clean)


CATALOG = {
    "TLKM": "Telkom Indonesia", "ASII": "Astra International", "ICBP": "Indofood CBP",
    "INDF": "Indofood Sukses Makmur", "UNVR": "Unilever Indonesia", "KLBF": "Kalbe Farma",
    "MYOR": "Mayora Indah", "SIDO": "Industri Jamu Sido Muncul",
    "INTP": "Indocement", "UNTR": "United Tractors", "ADRO": "Alamtri Resources Indonesia",
    "PTBA": "Bukit Asam", "ITMG": "Indo Tambangraya Megah", "ANTM": "Aneka Tambang",
    "AKRA": "AKR Corporindo", "PGAS": "Perusahaan Gas Negara", "MEDC": "Medco Energi Internasional",
}


def ticker_symbol(value):
    v = value.strip().upper()
    if v.endswith(".JK"):
        v = v[:-3]
    if not re.fullmatch(r"[A-Z0-9]{4}", v):
        raise ValueError("Enter a four-character IDX ticker, for example TLKM or TLKM.JK.")
    return v + ".JK"


def number(value):
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (TypeError, ValueError):
        return None


def pick(frame, period, *names):
    if frame.empty or period not in frame.columns:
        return None
    for name in names:
        if name in frame.index:
            n = number(frame.at[name, period])
            if n is not None:
                return n / BILLION
    # Case & whitespace-insensitive matching fallback for yfinance label variations
    norm_map = {re.sub(r"[^a-z0-9]", "", str(k).lower()): k for k in frame.index}
    for name in names:
        norm = re.sub(r"[^a-z0-9]", "", str(name).lower())
        if norm in norm_map:
            n = number(frame.at[norm_map[norm], period])
            if n is not None:
                return n / BILLION
    return None


def subtract(total, *parts):
    return total - sum(parts) if total is not None and all(p is not None for p in parts) else None


def normalize(income, balance, cashflow):
    records, provenance = {}, {}
    # A common fiscal period is required; never mix different closing dates.
    periods = sorted(set(income.columns) & set(balance.columns) & set(cashflow.columns))
    for period in periods:
        inc = lambda *keys: pick(income, period, *keys)
        bs = lambda *keys: pick(balance, period, *keys)
        cf = lambda *keys: pick(cashflow, period, *keys)
        p = {}

        def put(key, val, source):
            p[key] = val
            provenance[f"{pd.Timestamp(period).date()}:{key}"] = source if val is not None else "Missing — enter or explicitly accept zero"

        put("revenue", inc("TotalRevenue", "OperatingRevenue"), "Reported: revenue")
        cogs = inc("CostOfRevenue", "ReconciledCostOfRevenue")
        put("cogs", abs(cogs) if cogs is not None else None, "Reported: cost of revenue (positive expense)")
        da = cf("DepreciationAndAmortization", "DepreciationAmortizationDepletion")
        if da is None:
            da = inc("ReconciledDepreciation", "DepreciationAndAmortizationInIncomeStatement")
        put("da", abs(da) if da is not None else None, "Reported: D&A; used as total operating D&A")
        interest = inc("InterestExpense", "InterestExpenseNonOperating")
        interest_val = abs(interest) if interest is not None else 0.0
        put("interest", abs(interest) if interest is not None else None, "Reported: interest expense")

        # EBIT sanity validation: check for Yahoo Finance sign inversion where negative OpEx inflates OperatingIncome
        op_inc = inc("OperatingIncome")
        ebit_rep = inc("EBIT")
        pretax = inc("PretaxIncome")

        if op_inc is not None and pretax is not None and pretax > 0 and op_inc > pretax * 1.30:
            if ebit_rep is not None and abs(ebit_rep - pretax) < abs(op_inc - pretax):
                ebit = ebit_rep
            else:
                ebit = pretax + interest_val
        elif op_inc is not None:
            ebit = op_inc
        elif ebit_rep is not None:
            ebit = ebit_rep
        elif pretax is not None:
            ebit = pretax + interest_val
        else:
            ebit = None

        # EBITDA - EBIT provides a useful fallback when cash-flow D&A is absent.
        if p["da"] is None:
            put("da", subtract(inc("EBITDA"), ebit), "Calculated: EBITDA less EBIT")
        raw_opex = subtract(p["revenue"], p["cogs"], p["da"], ebit)
        if raw_opex is not None and raw_opex < 0:
            raw_opex = 0.0
        put("opex", raw_opex, "Calculated: revenue − COGS − D&A − EBIT")
        put("tax", inc("TaxProvision"), "Reported: tax provision")
        put("net_income", inc("NetIncomeCommonStockholders", "NetIncome"), "Reported: common-shareholder net income where available")

        # Damodaran Week 2 Slide 41 & 63: Prioritize Cash & Short-Term Marketable Securities together
        put("cash", bs("CashCashEquivalentsAndShortTermInvestments", "CashAndCashEquivalents"),
            "Reported: cash and short-term marketable securities")
        put("ar", bs("Receivables", "AccountsReceivable"), "Reported: receivables")
        put("inventory", bs("Inventory"), "Reported: inventory")
        put("other_ca", subtract(bs("CurrentAssets"), p["cash"], p["ar"], p["inventory"]),
            "Calculated: current assets less cash and marketable securities, receivables and inventory")
        put("ppe", bs("NetPPE"), "Reported: net PPE")
        put("other_assets", subtract(bs("TotalAssets"), bs("CurrentAssets"), p["ppe"]),
            "Calculated: assets less current assets and PPE")

        # Non-operating assets (Holdings in associates, equity investments, investment properties per Damodaran Week 2 Slide 63)
        nonop = bs("InvestmentsinAssociatesatCost", "LongTermEquityInvestment", "InvestmentProperties", "AvailableForSaleSecurities")
        p["nonoperating_assets"] = nonop

        put("ap", bs("AccountsPayable"), "Reported: accounts payable")
        put("short_debt", bs("CurrentDebtAndCapitalLeaseObligation", "CurrentDebt"),
            "Reported: current debt including leases where available")
        long_debt = bs("LongTermDebtAndCapitalLeaseObligation", "LongTermDebt")
        put("long_debt", long_debt if long_debt is not None else subtract(bs("TotalDebt"), p["short_debt"]),
            "Reported/derived: non-current debt")
        put("other_cl", subtract(bs("CurrentLiabilities"), p["ap"], p["short_debt"]),
            "Calculated: current liabilities less payables and current debt")
        put("other_liabilities", subtract(bs("TotalLiabilitiesNetMinorityInterest"), bs("CurrentLiabilities"), p["long_debt"]),
            "Calculated: liabilities less current liabilities and long-term debt")
        put("equity", bs("TotalEquityGrossMinorityInterest", "StockholdersEquity"),
            "Reported: total equity; review minority interests separately")
        p["ebit"] = ebit
        p["ebitda"] = ebit + p["da"] if ebit is not None and p["da"] is not None else None
        p["cfo"] = cf("OperatingCashFlow", "CashFlowFromContinuingOperatingActivities", "CashFlowsfromusedinOperatingActivitiesDirect")
        capex = cf("CapitalExpenditure")
        p["capex"] = abs(capex) if capex is not None else None

        # Minority Interest (Non-Controlling Interest per Damodaran Week 2 Slide 63 & Week 4 Slide 8, 23)
        mi = bs("MinorityInterest")
        if mi is None and bs("TotalEquityGrossMinorityInterest") is not None and bs("StockholdersEquity") is not None:
            mi = subtract(bs("TotalEquityGrossMinorityInterest"), bs("StockholdersEquity"))
        p["minority_interest"] = mi
        p["common_equity"] = subtract(p["equity"], mi) if mi is not None else p.get("equity")

        records[str(pd.Timestamp(period).date())] = p
    frame = pd.DataFrame(records).apply(pd.to_numeric, errors="coerce")
    # Drop placeholder periods where all base accounts are empty
    core_mask = frame.loc[[k for k in BASE_FIELDS if k in frame.index]].notna().any(axis=0)
    frame = frame.loc[:, core_mask]
    return frame, provenance


def clean_company_name(name: str) -> str:
    """Sanitize Indonesian company names by stripping cumbersome legal prefixes
    such as 'Perusahaan Perseroan (Persero)' commonly returned by Yahoo Finance.
    """
    if not name:
        return ""
    cleaned = re.sub(r"^\s*perusahaan\s+perseroan\s*\(persero\)\s*", "", name, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bperusahaan\s+perseroan\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\(persero\)", "", cleaned, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", cleaned).strip()


def fetch_company(symbol):
    symbol = ticker_symbol(symbol)
    cache = Path(__file__).resolve().parents[1] / "data" / "yfinance"
    cache.mkdir(parents=True, exist_ok=True)
    yf.set_tz_cache_location(str(cache))
    session = get_doh_session()
    t = yf.Ticker(symbol, session=session)
    info = t.get_info()
    income = t.get_income_stmt(freq="yearly")
    balance = t.get_balance_sheet(freq="yearly")
    cashflow = t.get_cashflow(freq="yearly")
    if any(x.empty for x in (income, balance, cashflow)):
        raise ValueError(f"Yahoo returned incomplete annual statements for {symbol}. Try again later or use another ticker.")
    historical, provenance = normalize(income, balance, cashflow)
    if historical.empty:
        raise ValueError("No common annual fiscal dates across all three statements.")

    # 5-Year monthly regression Beta against the Jakarta Composite Index (^JKSE)
    reg_beta = None
    try:
        p_hist = t.history(period="5y", interval="1mo")["Close"].pct_change().dropna()
        idx_hist = yf.Ticker("^JKSE", session=session).history(period="5y", interval="1mo")["Close"].pct_change().dropna()
        comb = pd.concat([p_hist, idx_hist], axis=1).dropna()
        if len(comb) >= 12:
            cov = comb.cov().iloc[0, 1]
            var_m = comb.iloc[:, 1].var()
            if var_m > 0:
                reg_beta = float(cov / var_m)
    except Exception:
        reg_beta = None

    if reg_beta is not None and math.isfinite(reg_beta):
        beta = reg_beta
    else:
        # Fallback to yfinance reported beta or default 1.0
        beta = number(info.get("beta")) or 1.0

    # Handle financial currency conversion for USD-reporting IDX issuers
    fin_curr = info.get("financialCurrency", "IDR")
    price_curr = info.get("currency", "IDR")
    suggested_fx = 1.0
    if fin_curr and fin_curr != "IDR" and price_curr == "IDR":
        try:
            fx_sym = f"{fin_curr}IDR=X"
            fx_ticker = yf.Ticker(fx_sym, session=session)
            fx_rate = fx_ticker.fast_info.get("lastPrice") or fx_ticker.info.get("regularMarketPrice")
            if fx_rate and math.isfinite(fx_rate) and fx_rate > 0:
                suggested_fx = float(fx_rate)
        except Exception:
            suggested_fx = 16000.0 if fin_curr == "USD" else 1.0

    # Sector, Sub-Industry, and official Stock Name are strictly sourced from repository IDX Excel
    clean_sym = symbol.replace(".JK", "").strip().upper()
    idx_meta = get_company_idx_metadata(clean_sym)
    official_name = idx_meta["name"] if idx_meta else clean_company_name(info.get("longName", symbol))
    official_sector = idx_meta["sector"] if idx_meta else info.get("sector", "Unknown")
    official_industry = idx_meta["sub_industry"] if idx_meta else info.get("industry", "Unknown")

    return dict(
        symbol=symbol,
        name=official_name,
        sector=official_sector,
        industry=official_industry,
        financial_currency=fin_curr,
        price_currency=price_curr,
        suggested_fx=suggested_fx,
        price=number(info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose") or (getattr(t, "fast_info", None) and getattr(t.fast_info, "get", lambda _: None)("lastPrice"))),
        shares=number(info.get("sharesOutstanding")),
        beta=beta,
        market_cap=number(info.get("marketCap")),
        fetched_at=datetime.now(timezone.utc).isoformat(),
        historical=historical,
        provenance=provenance,
        raw={"Income statement": income, "Balance sheet": balance, "Cash flow": cashflow},
        demo=False,
    )


def demo_company():
    # Intentionally fictional; never presented as a real IDX security.
    base = dict(revenue=10000., cogs=6000., opex=1700., da=500., interest=160., tax=360.8, net_income=1279.2,
                cash=1500., ar=1200., inventory=1000., other_ca=200., ppe=4500., other_assets=1600.,
                ap=900., other_cl=400., short_debt=300., long_debt=1700., other_liabilities=700., equity=6000.)
    hist = {}
    for year, scale in [(2022, .78), (2023, .85), (2024, .93), (2025, 1.)]:
        row = {k: v * scale for k, v in base.items()}
        row.update(
            ebit=1800 * scale,
            ebitda=2300 * scale,
            cfo=1600 * scale,
            capex=600 * scale,
            minority_interest=1100.0 * scale,
            common_equity=4900.0 * scale,
            nonoperating_assets=0.0,
        )
        hist[f"{year}-12-31"] = row
    return dict(
        symbol="DEMO",
        name="Nusantara Consumer · Fictional company",
        sector="Consumer Defensive",
        industry="Illustrative consumer business",
        financial_currency="IDR",
        price_currency="IDR",
        suggested_fx=1.0,
        price=1250.,
        shares=8e9,
        beta=1.,
        market_cap=10000e9,
        fetched_at="Illustrative data, not market data",
        historical=pd.DataFrame(hist),
        provenance={},
        raw={},
        demo=True,
    )


def demo_peers():
    """Returns 2 illustrative peer company dictionaries for the fictional demo."""
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


IDX_INDUSTRY_PEERS = {
    # Thermal Coal / Mining (IDX-IC: Coal Production)
    "Coal Production": ["ADRO", "PTBA", "ITMG", "BUMI", "INDY", "HRUM", "ADMR"],
    "Thermal Coal": ["ADRO", "PTBA", "ITMG", "BUMI", "INDY", "HRUM", "ADMR"],
    # Oil & Gas
    "Oil & Gas Storage & Distribution": ["AKRA", "PGAS", "MEDC", "ENRG"],
    "Oil & Gas Production & Refinery": ["MEDC", "PGAS", "ENRG", "AKRA"],
    "Oil & Gas Refining & Marketing": ["AKRA", "PGAS", "MEDC"],
    "Oil & Gas E&P": ["MEDC", "PGAS", "ENRG"],
    # Consumer Non-Cyclicals / Personal Care (IDX-IC: Personal Care Products)
    "Personal Care Products": ["UNVR", "VICI", "TCID", "KINO", "MYOR", "ICBP"],
    "Household & Personal Products": ["UNVR", "VICI", "TCID", "KINO", "MYOR", "ICBP"],
    # Processed Foods / Packaged Foods
    "Processed Foods": ["ICBP", "INDF", "MYOR", "UNVR", "ROTI", "ULTJ"],
    "Packaged Foods": ["ICBP", "INDF", "MYOR", "UNVR", "ROTI", "ULTJ"],
    # Pharmaceuticals
    "Pharmaceuticals": ["KLBF", "SIDO", "TSPC", "KAEF"],
    "Drug Manufacturers - General": ["KLBF", "SIDO", "TSPC", "KAEF"],
    # Cement & Building Materials
    "Building Materials": ["SMGR", "INTP", "SMBR"],
    # Industrial Conglomerates
    "Industrial Conglomerates": ["ASII", "UNTR"],
    # Agriculture / Plantation (IDX-IC: Plantations & Crops)
    "Plantations & Crops": ["TAPG", "AALI", "LSIP", "DSNG", "SIMP", "BWPT", "SSMS"],
    "Farm Products": ["TAPG", "AALI", "LSIP", "DSNG", "SIMP", "BWPT", "SSMS"],
    "Agricultural Inputs": ["TAPG", "AALI", "LSIP", "DSNG", "SIMP"],
    # Telecom Services (IDX-IC Industry Group J3: Telecommunication Services)
    "Integrated Telecommunication Service": ["ISAT", "EXCL", "TOWR", "TBIG", "MTEL"],
    "Wireless Telecommunication Services": ["ISAT", "EXCL", "TLKM", "TOWR", "TBIG", "MTEL"],
    "Wired Telecommunication Service": ["LINK", "MORA", "TLKM", "ISAT", "EXCL"],
    "Telecommunication Services": ["TLKM", "ISAT", "EXCL", "TOWR", "TBIG", "MTEL"],
    "Telecom Services": ["TLKM", "ISAT", "EXCL", "TOWR", "TBIG", "MTEL"],
}


def get_default_peers_for_ticker(symbol, industry=None):
    """Returns candidate peer tickers for a given symbol based on official IDX sub-industry mapping.
    Industry/Sub-industry is sourced strictly from 'book/Company LIsted on IDX.xlsx'.
    For singleton or small sub-industries (such as TLKM's 'Integrated Telecommunication Service'),
    peers are matched with sibling companies within the same official 2-digit IDX-IC Industry Group
    (e.g. 'J3' Telecommunication Services: ISAT, EXCL, TOWR, TBIG, MTEL), strictly avoiding
    unrelated sub-industries like Toll Roads or Airports.
    """
    clean = symbol.replace(".JK", "").upper()
    ticker_map, sub_ind_map, sector_map, group_map = load_idx_company_registry(include_groups=True)

    candidates = []
    seen = set()

    # Look up metadata from registry
    target_meta = ticker_map.get(clean, {})
    sub_ind = target_meta.get("sub_industry") or industry
    group_code = target_meta.get("group_code", "")
    sec = target_meta.get("sector", "")

    # Priority 1: Curated peers directly matching sub-industry or ticker
    curated_candidates = []
    if sub_ind and sub_ind in IDX_INDUSTRY_PEERS:
        curated_candidates.extend(IDX_INDUSTRY_PEERS[sub_ind])

    for group in IDX_INDUSTRY_PEERS.values():
        if clean in group:
            for t in group:
                if t != clean and t not in curated_candidates:
                    curated_candidates.append(t)

    for t in curated_candidates:
        if t != clean and t not in seen:
            candidates.append(t)
            seen.add(t)

    # Priority 2: Candidates in the exact same Sub-Industry
    same_sub = [t for t in sub_ind_map.get(sub_ind, []) if t != clean]
    for t in same_sub:
        if t not in seen:
            candidates.append(t)
            seen.add(t)

    # Priority 3: Sibling peers within the official 2-digit IDX-IC Industry Group (e.g. 'J3' Telecommunication Services).
    # Essential for singleton or small sub-industries (like TLKM's Integrated Telecommunication Service)
    # so they pair with genuine industry peers rather than falling back to unrelated sector sub-industries.
    if group_code:
        sibling_group_peers = [t for t in group_map.get(group_code, []) if t != clean]
        for t in sibling_group_peers:
            if t not in seen:
                candidates.append(t)
                seen.add(t)

    # Priority 4: Fallback to broader Sector only if no sub-industry or industry-group peers exist at all
    if len(candidates) < 2 and sec:
        sec_peers = [t for t in sector_map.get(sec, []) if t != clean]
        for t in sec_peers:
            if t not in seen:
                candidates.append(t)
                seen.add(t)

    # Priority 5: Default fallbacks within general blue chips if none matched
    if not candidates:
        for t in ["ISAT", "EXCL", "ADRO", "PTBA", "AKRA", "PGAS"]:
            if t != clean and t not in seen:
                candidates.append(t)
                seen.add(t)

    return candidates


def get_or_fetch_peers(tickers, target_symbol=None):
    """Loads peer company dictionaries for the requested tickers,
    excluding target_symbol and skipping financial companies.
    Uses resilient session with error isolation.
    """
    clean_target = (target_symbol or "").replace(".JK", "").upper()
    results = []
    errors = []
    seen = set()
    for t in tickers:
        t_clean = t.strip().upper()
        if not t_clean or t_clean in seen:
            continue
        seen.add(t_clean)
        try:
            sym = ticker_symbol(t_clean)
            clean = sym.replace(".JK", "").upper()
            if clean == clean_target:
                continue
            pc = fetch_company(sym)
            if pc.get("sector") == "Financial Services":
                continue
            results.append(pc)
        except Exception as e:
            errors.append(f"{t_clean}: {e}")
    return results, errors


def peer_record(company, period, fx=None, claims=None):
    h = company["historical"]
    if period not in h.columns:
        raise ValueError(f"No matching fiscal period {period}; excluded rather than mixing periods.")
    if company["price_currency"] != "IDR":
        raise ValueError("Price currency is not verified as IDR.")
    price, shares = company["price"], company["shares"]
    if not price or not shares:
        raise ValueError("Market price or shares unavailable.")

    # Unconditional financial currency alignment for USD/foreign-reporting IDX issuers
    fin_curr = (company.get("financial_currency") or "IDR").upper()
    if fin_curr != "IDR":
        if fx is None or fx <= 1.0:
            fx = float(company.get("suggested_fx", 16000.0 if fin_curr == "USD" else 1.0))
        p = h[period] * fx
    else:
        p = h[period]
    if any(pd.isna(p.get(k)) for k in ("cash", "short_debt", "long_debt")):
        raise ValueError("Cash or debt unavailable; cannot calculate a comparable EV.")
    market_cap = price * shares / BILLION

    # Clean EV calculation strictly from reported financial statements (no manual adjustments)
    nci = 0.0 if pd.isna(p.get("minority_interest")) else float(p["minority_interest"])
    tot_debt = float(p.short_debt + p.long_debt)
    book_eq = float(p["common_equity"]) if "common_equity" in p and pd.notna(p["common_equity"]) else float(p.equity)
    inv_cap = float(p.short_debt + p.long_debt + p.equity - p.cash)

    rev_val = float(p.revenue) if pd.notna(p.get("revenue")) else None
    ebitda_val = float(p.ebitda) if pd.notna(p.get("ebitda")) else None
    margin = (ebitda_val / rev_val) if rev_val and ebitda_val and rev_val > 0 else None
    der = (tot_debt / book_eq) if book_eq and book_eq > 0 else None

    return dict(
        ticker=company["symbol"],
        name=company["name"],
        period=period,
        industry=company.get("industry", "Unknown"),
        sector=company.get("sector", "Unknown"),
        market_cap=market_cap,
        total_debt=tot_debt,
        ev=market_cap + tot_debt - float(p.cash) + nci,
        book_equity=book_eq,
        invested_capital=inv_cap,
        ebitda_margin=margin,
        der=der,
        **{k: None if pd.isna(p.get(k)) else float(p[k]) for k in ("revenue", "ebitda", "ebit", "net_income")}
    )


def rank_peers_similarity(target_profile, candidate_records):
    """Ranks candidate peer records based purely on financial similarity to target:
    - 60% Weight: Normalized EBITDA Margin distance (operational profitability)
    - 40% Weight: Normalized Debt-to-Equity DER distance (capital structure risk)
    Sub-industry matching is enforced as the first-stage gating filter,
    so no penalty is added to the financial distance.
    Returns candidates sorted by ascending similarity distance (descending similarity score).
    """
    target_margin = target_profile.get("ebitda_margin")
    target_der = target_profile.get("der")

    ranked = []
    for rec in candidate_records:
        rec_margin = rec.get("ebitda_margin")
        rec_der = rec.get("der")

        # Pure financial distance on normalized EBITDA Margin and DER
        # Normalizers: margin std ~15%, DER std ~60%
        m_diff = abs((rec_margin - target_margin) / 0.15) if (rec_margin is not None and target_margin is not None) else 2.0
        d_diff = abs((rec_der - target_der) / 0.60) if (rec_der is not None and target_der is not None) else 2.0
        dist = 0.60 * m_diff + 0.40 * d_diff

        r = dict(rec)
        r["similarity_distance"] = round(dist, 4)
        score = max(0, min(100, int(round(100.0 / (1.0 + (dist / 1.5))))))
        confidence = "High" if score >= 75 else ("Moderate" if score >= 50 else "Low")
        r["similarity_score"] = score
        r["confidence_level"] = confidence
        ranked.append(r)

    ranked.sort(key=lambda x: x["similarity_distance"])
    return ranked
