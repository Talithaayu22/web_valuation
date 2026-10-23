"""All money is in IDR billions; shares are in billions. Rates are decimals.

Annual, year-end FCFF model. Interest uses opening debt (avoids circularity).
Other balance sheet buckets are held constant. Cash shortfalls are funded by
explicit revolver draws; cash surpluses are retained. No interest income, NOL
schedule, new share issuance, or future acquisitions are assumed.
"""
from dataclasses import dataclass, asdict
import math
import numpy as np
import pandas as pd


BASE_FIELDS = {
    "revenue": "Revenue", "cogs": "Cost of goods sold", "opex": "Operating expenses (excl. D&A)",
    "da": "Depreciation & amortization", "interest": "Interest expense", "tax": "Income tax",
    "net_income": "Net income", "cash": "Cash & equivalents", "ar": "Receivables",
    "inventory": "Inventory", "other_ca": "Other operating current assets", "ppe": "Net fixed assets",
    "other_assets": "Other non-current assets", "ap": "Trade payables",
    "other_cl": "Other operating current liabilities", "short_debt": "Short-term debt",
    "long_debt": "Long-term debt", "other_liabilities": "Other non-current liabilities", "equity": "Total equity",
}


@dataclass
class Assumptions:
    growth: float = .08
    mature_growth: float = .04
    ebit_margin: float = .18
    mature_margin: float = .18
    gross_margin: float = .40
    capex_pct: float = .06
    depreciation_rate: float = .12
    ar_days: float = 45
    inventory_days: float = 60
    ap_days: float = 50
    other_ca_pct: float = .02
    other_cl_pct: float = .04
    tax_rate: float = .22
    debt_rate: float = .08
    annual_repayment: float = 0
    dividend_payout: float = .30
    minimum_cash_pct: float = .02
    risk_free: float = .065
    beta: float = 1.0
    equity_premium: float = .06
    debt_weight: float = .20
    wacc_override: float | None = None
    terminal_growth: float = .035
    terminal_roic: float = .15
    other_claims: float = 0
    nonoperating_assets: float = 0

    @property
    def cost_of_equity(self):
        return self.risk_free + self.beta * self.equity_premium

    @property
    def wacc(self):
        if self.wacc_override is not None:
            return self.wacc_override
        return self.cost_of_equity * (1 - self.debt_weight) + self.debt_rate * (1 - self.tax_rate) * self.debt_weight


def base_check(b):
    assets = sum(b[k] for k in ("cash", "ar", "inventory", "other_ca", "ppe", "other_assets"))
    claims = sum(b[k] for k in ("ap", "other_cl", "short_debt", "long_debt", "other_liabilities", "equity"))
    return assets - claims


def default_drivers(a, first_year):
    return pd.DataFrame({
        "Year": range(first_year, first_year + 10),
        "Growth %": [100 * a.growth] * 5 + list(np.linspace(a.growth, a.mature_growth, 6)[1:] * 100),
        "EBIT margin %": [100 * a.ebit_margin] * 5 + list(np.linspace(a.ebit_margin, a.mature_margin, 6)[1:] * 100),
        "Capex / sales %": [100 * a.capex_pct] * 10,
    })


def forecast(b, a, first_year, drivers=None):
    if not all(math.isfinite(float(b[k])) for k in BASE_FIELDS):
        raise ValueError("Every opening financial input must be a finite number.")
    if b["revenue"] <= 0:
        raise ValueError("Opening revenue must be positive.")
    if abs(base_check(b)) > max(0.01, abs(b["equity"]) * 1e-6):
        raise ValueError("Opening balance sheet does not balance. Correct the historical inputs first.")
    for name, value in asdict(a).items():
        if value is not None and not math.isfinite(value):
            raise ValueError(f"Invalid assumption: {name}")
    if not (0 <= a.tax_rate < 1 and 0 <= a.dividend_payout <= 1 and 0 < a.gross_margin <= 1):
        raise ValueError("Check tax, payout, and gross margin assumptions.")
    if min(a.ar_days, a.inventory_days, a.ap_days, a.annual_repayment, a.depreciation_rate) < 0:
        raise ValueError("Days, repayments, and depreciation cannot be negative.")
    d = default_drivers(a, first_year) if drivers is None else drivers.copy()
    if len(d) != 10 or list(d["Year"]) != list(range(first_year, first_year + 10)):
        raise ValueError("The forecast needs exactly 10 consecutive annual periods.")
    if not np.isfinite(d.to_numpy(dtype=float)).all():
        raise ValueError("Annual assumptions cannot be blank or non-finite.")
    if (d["Growth %"] <= -100).any() or (d["Capex / sales %"] < 0).any():
        raise ValueError("Growth must exceed −100% and capex cannot be negative.")
    p = dict(b)
    p["nwc"] = b["ar"] + b["inventory"] + b["other_ca"] - b["ap"] - b["other_cl"]
    result = []
    for _, row in d.iterrows():
        revenue = p["revenue"] * (1 + row["Growth %"] / 100)
        cogs = revenue * (1 - a.gross_margin)
        ebit = revenue * row["EBIT margin %"] / 100
        capex = revenue * row["Capex / sales %"] / 100
        da = min(p["ppe"] + capex, p["ppe"] * a.depreciation_rate)
        opex = revenue - cogs - da - ebit
        if opex < -1e-6:
            raise ValueError("Gross margin is too low for the requested EBIT margin and depreciation. Increase gross margin or lower EBIT margin.")
        opening_debt = p["short_debt"] + p["long_debt"]
        interest = opening_debt * a.debt_rate
        tax = max(0, ebit - interest) * a.tax_rate
        net_income = ebit - interest - tax
        ar = revenue * a.ar_days / 365
        inventory = cogs * a.inventory_days / 365
        ap = cogs * a.ap_days / 365
        other_ca, other_cl = revenue * a.other_ca_pct, revenue * a.other_cl_pct
        nwc = ar + inventory + other_ca - ap - other_cl
        delta_nwc = nwc - p["nwc"]
        cfo = net_income + da - delta_nwc
        dividends = max(0, net_income) * a.dividend_payout
        repayment = min(opening_debt, a.annual_repayment)
        short_repay = min(p["short_debt"], repayment)
        cash_before_draw = p["cash"] + cfo - capex - dividends - repayment
        funding = max(0, revenue * a.minimum_cash_pct - cash_before_draw)
        cash = cash_before_draw + funding
        short_debt = p["short_debt"] - short_repay + funding
        long_debt = p["long_debt"] - (repayment - short_repay)
        ppe = p["ppe"] + capex - da
        equity = p["equity"] + net_income - dividends
        assets = cash + ar + inventory + other_ca + ppe + b["other_assets"]
        liabilities = ap + other_cl + short_debt + long_debt + b["other_liabilities"]
        f = dict(year=int(row["Year"]), revenue=revenue, cogs=cogs, opex=opex, da=da,
                 ebitda=ebit + da, ebit=ebit, interest=interest, tax=tax, net_income=net_income,
                 cash=cash, ar=ar, inventory=inventory, other_ca=other_ca, ppe=ppe,
                 other_assets=b["other_assets"], ap=ap, other_cl=other_cl, short_debt=short_debt,
                 long_debt=long_debt, other_liabilities=b["other_liabilities"], equity=equity,
                 assets=assets, liabilities=liabilities, nwc=nwc, delta_nwc=delta_nwc,
                 capex=capex, cfo=cfo, cfi=-capex, cff=funding-repayment-dividends,
                 funding=funding, repayment=repayment, dividends=dividends,
                 cash_change=cash-p["cash"], balance_check=assets-liabilities-equity,
                 fcff=ebit * (1-a.tax_rate) + da - capex - delta_nwc)
        result.append(f)
        p = f
    return pd.DataFrame(result).set_index("year")


def dcf(f, b, a, shares):
    if not math.isfinite(shares) or shares <= 0:
        raise ValueError("Shares outstanding must be greater than zero.")
    w, g = a.wacc, a.terminal_growth
    if not (w > g >= 0):
        raise ValueError("WACC must exceed terminal growth, and terminal growth cannot be negative.")
    if a.terminal_roic <= g:
        raise ValueError("Terminal ROIC must exceed terminal growth to support positive terminal cash flow.")
    terminal_nopat = float(f.iloc[-1].ebit) * (1-a.tax_rate) * (1+g)
    if terminal_nopat <= 0:
        raise ValueError("Year 10 operating profit must be positive for this terminal-value method.")
    # Sustainable terminal reinvestment = growth / ROIC, rather than extrapolating
    # a potentially unsustainable final-year capital expenditure assumption.
    terminal_fcff = terminal_nopat * (1-g/a.terminal_roic)
    terminal_value = terminal_fcff / (w-g)
    pv_flows = sum(float(v)/(1+w)**i for i,v in enumerate(f.fcff, 1))
    pv_terminal = terminal_value/(1+w)**len(f)
    ev = pv_flows + pv_terminal
    eq = ev + b["cash"] + a.nonoperating_assets - b["short_debt"] - b["long_debt"] - a.other_claims
    return dict(wacc=w, terminal_fcff=terminal_fcff, terminal_value=terminal_value,
                pv_flows=pv_flows, pv_terminal=pv_terminal, enterprise_value=ev,
                equity_value=eq, price=eq/shares, terminal_share=pv_terminal/ev if ev else 0)


def sensitivity(f, b, a, shares):
    from dataclasses import replace
    ws = [a.wacc + x for x in (-.02,-.01,0,.01,.02)]
    gs = [max(0,a.terminal_growth + x) for x in (-.01,-.005,0,.005,.01)]
    grid = []
    for w in ws:
        vals = []
        for g in gs:
            try:
                vals.append(dcf(f,b,replace(a,wacc_override=w,terminal_growth=g),shares)["price"])
            except ValueError:
                vals.append(float("nan"))
        grid.append(vals)
    return pd.DataFrame(grid,index=[f"{w:.2%}" for w in ws],columns=[f"{g:.2%}" for g in gs])


def relative_values(peers, target, cash, debt, shares, other_claims=0, nonoperating_assets=0):
    """Peer rows and target denominators must use the same annual period basis.
    Enterprise multiples exclude negative EV and non-positive denominators.
    """
    if shares <= 0:
        raise ValueError("Shares must be positive.")
    rows = []
    for label, metric, numerator in [("EV / Revenue","revenue","ev"),("EV / EBITDA","ebitda","ev"),
                                     ("EV / EBIT","ebit","ev"),("P / E","net_income","market_cap")]:
        multiples = []
        for p in peers:
            den, num = p.get(metric), p.get(numerator)
            if den is not None and num is not None and math.isfinite(den) and math.isfinite(num) and den > 0 and num > 0:
                multiples.append(num/den)
        for percentile, name in [(25,"Lower quartile"),(50,"Median"),(75,"Upper quartile")]:
            mult = float(np.percentile(multiples,percentile)) if multiples else float("nan")
            denominator = target.get(metric)
            value = mult * denominator if denominator is not None and denominator > 0 else float("nan")
            equity = value + cash + nonoperating_assets - debt - other_claims if numerator == "ev" else value
            rows.append({"Multiple":label,"Case":name,"Peers used":len(multiples),"Peer multiple":mult,"Implied price (IDR)":equity/shares})
    return pd.DataFrame(rows)
