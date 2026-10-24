"""All money is in IDR billions; shares are in billions. Rates are decimals.

Annual, year-end FCFF model. Interest uses opening debt (avoids circularity).
Other balance sheet buckets are held constant. Cash shortfalls are funded by
explicit revolver draws; cash surpluses are retained.
Aligned with Aswath Damodaran's DCF (FCFF) and Relative Valuation framework.
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
    # 01 Operating model: Operating & reinvestment
    growth: float = .08
    mature_growth: float = .025
    ebit_margin: float = .18
    mature_margin: float = .18
    gross_margin: float = .40
    capex_pct: float = .06
    depreciation_rate: float = .12
    nwc_pct: float | None = None          # Damodaran Non-Cash Working Capital as % of revenue (defaults to baseline ratio)
    tax_rate: float = .22
    minimum_cash_pct: float = .02
    dividend_payout: float = .30
    annual_repayment: float = 0.0

    # Backward compatibility fields for turnover days
    ar_days: float = 45.0
    inventory_days: float = 60.0
    ap_days: float = 50.0
    other_ca_pct: float = .02
    other_cl_pct: float = .04

    # 02 Macro & WACC: Capital market assumptions
    risk_free: float = .0664             # Dec 31, 2025 benchmark: Indonesian 10Y Government Bond (FR series)
    mature_equity_premium: float = .0460 # Damodaran published NYU Stern mature market ERP
    country_risk_premium: float = .0218  # Damodaran published Indonesia CRP (Baa2 / BBB spread * equity volatility)
    beta: float = 1.0
    debt_rate: float = .08
    debt_weight: float = .20
    wacc_override: float | None = None
    equity_premium: float = .0460        # Backward-compatible alias

    # 03 Valuation policy: Methods & scenarios
    terminal_growth: float = .025
    terminal_roic: float = .15
    other_claims: float = 0.0
    nonoperating_assets: float = 0.0
    dcf_weight: float = 0.75
    relative_weight: float = 0.25
    scenario_shift: float = 0.02
    scenario_mode: str = "Coherent Macro & Operating World"
    bear_growth_shift: float = -0.02
    bull_growth_shift: float = 0.02
    bear_margin_shift: float = -0.02
    bull_margin_shift: float = 0.02
    bear_wacc_shift: float = 0.005
    bull_wacc_shift: float = -0.005
    bear_g_shift: float = -0.005
    bull_g_shift: float = 0.005
    bear_roic_shift: float = -0.010
    bull_roic_shift: float = 0.010
    bear_reinvest_shift: float = 0.010
    bull_reinvest_shift: float = -0.010

    # Scenario Probabilities (Institutionally Governed: Bear 20-25%, Base 50-60%, Bull 20-25%)
    prob_bear: float = 0.25
    prob_base: float = 0.50
    prob_bull: float = 0.25

    def normalized_scenario_probabilities(self) -> dict[str, float]:
        """Returns normalized probabilities for Bear, Base, and Bull scenarios summing to 1.0."""
        total = self.prob_bear + self.prob_base + self.prob_bull
        if total <= 0:
            return {"Bear": 0.25, "Base": 0.50, "Bull": 0.25}
        return {
            "Bear": self.prob_bear / total,
            "Base": self.prob_base / total,
            "Bull": self.prob_bull / total,
        }

    @property
    def total_equity_premium(self):
        return self.mature_equity_premium + self.country_risk_premium

    @property
    def cost_of_equity(self):
        # Damodaran standard: Beta scales Total ERP (Mature ERP + CRP)
        return self.risk_free + self.beta * self.total_equity_premium

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
    # 5-Year Explicit Forecast Horizon (Years 1-3 Operational Momentum, Years 4-5 Convergence)
    growth_y4 = a.growth * (2.0 / 3.0) + a.mature_growth * (1.0 / 3.0)
    growth_y5 = a.mature_growth

    margin_y4 = a.ebit_margin * (2.0 / 3.0) + a.mature_margin * (1.0 / 3.0)
    margin_y5 = a.mature_margin

    return pd.DataFrame({
        "Year": range(first_year, first_year + 5),
        "Growth %": [100 * a.growth, 100 * a.growth, 100 * a.growth, 100 * growth_y4, 100 * growth_y5],
        "EBIT margin %": [100 * a.ebit_margin, 100 * a.ebit_margin, 100 * a.ebit_margin, 100 * margin_y4, 100 * margin_y5],
        "Capex / sales %": [100 * a.capex_pct] * 5,
    })


def compute_historical_roic(historical, b=None, tax_rate=0.22):
    """Calculates historical median ROIC (NOPAT / Invested Capital) across audited periods.
    Invested Capital = PPE + Non-Cash NWC + Other Operating Assets.
    If operating IC is unavailable or <= 0, financing approach (Debt + Equity - Cash) is used.
    NOPAT = EBIT * (1 - tax_rate).
    """
    roics = []
    if historical is not None and not historical.empty:
        for col in historical.columns:
            period_data = historical[col]
            ebit = period_data.get("ebit")
            if ebit is None or pd.isna(ebit):
                rev = period_data.get("revenue")
                cogs = period_data.get("cogs", 0.0) or 0.0
                opex = period_data.get("opex", 0.0) or 0.0
                da = period_data.get("da", 0.0) or 0.0
                if rev is not None and pd.notna(rev):
                    ebit = float(rev) - float(cogs) - float(opex) - float(da)
            if ebit is not None and pd.notna(ebit):
                try:
                    nopat = float(ebit) * (1.0 - tax_rate)
                    ppe = float(period_data.get("ppe") or 0.0)
                    ar = float(period_data.get("ar") or 0.0)
                    inv = float(period_data.get("inventory") or 0.0)
                    other_ca = float(period_data.get("other_ca") or 0.0)
                    ap = float(period_data.get("ap") or 0.0)
                    other_cl = float(period_data.get("other_cl") or 0.0)
                    other_assets = float(period_data.get("other_assets") or 0.0)

                    nwc = ar + inv + other_ca - ap - other_cl
                    ic = ppe + nwc + other_assets
                    if ic <= 0:
                        sd = float(period_data.get("short_debt") or 0.0)
                        ld = float(period_data.get("long_debt") or 0.0)
                        eq = float(period_data.get("equity") or 0.0)
                        cash = float(period_data.get("cash") or 0.0)
                        ic = sd + ld + eq - cash
                    if ic > 0:
                        r = nopat / ic
                        if math.isfinite(r):
                            roics.append(r)
                except (TypeError, ValueError):
                    pass

    if not roics and b is not None:
        try:
            r = float(b.get("revenue", 0.0) or 0.0)
            ebit_val = b.get("ebit") if b.get("ebit") is not None else (r - float(b.get("cogs", 0.0) or 0.0) - float(b.get("opex", 0.0) or 0.0) - float(b.get("da", 0.0) or 0.0))
            if ebit_val is not None and pd.notna(ebit_val):
                nopat = float(ebit_val) * (1.0 - tax_rate)
                nwc = float(b.get("ar", 0.0) or 0.0) + float(b.get("inventory", 0.0) or 0.0) + float(b.get("other_ca", 0.0) or 0.0) - float(b.get("ap", 0.0) or 0.0) - float(b.get("other_cl", 0.0) or 0.0)
                ic = float(b.get("ppe", 0.0) or 0.0) + nwc + float(b.get("other_assets", 0.0) or 0.0)
                if ic <= 0:
                    ic = float(b.get("short_debt", 0.0) or 0.0) + float(b.get("long_debt", 0.0) or 0.0) + float(b.get("equity", 0.0) or 0.0) - float(b.get("cash", 0.0) or 0.0)
                if ic > 0:
                    r = nopat / ic
                    if math.isfinite(r):
                        roics.append(r)
        except (TypeError, ValueError):
            pass

    if roics:
        med = float(np.median(roics))
        return max(0.03, min(0.60, med))
    return 0.15


def infer_assumptions(historical, b, company=None):
    """Derives baseline assumptions from historical data aligned with Damodaran methodology."""
    a = Assumptions()
    r = b.get("revenue", 0.0)
    if r > 0:
        # Operating margins
        ebit_val = b.get("ebit") if b.get("ebit") is not None else (r - b.get("cogs", 0) - b.get("opex", 0) - b.get("da", 0))
        a.ebit_margin = max(-0.20, min(0.60, ebit_val / r))
        a.mature_margin = a.ebit_margin
        a.gross_margin = max(0.05, min(0.95, 1.0 - (b.get("cogs", 0) / r)))

        # Damodaran Non-Cash Working Capital as % of revenue (replaces granular turnover days)
        base_nwc = (b.get("ar", 0) + b.get("inventory", 0) + b.get("other_ca", 0) - b.get("ap", 0) - b.get("other_cl", 0))
        a.nwc_pct = max(-0.20, min(0.60, base_nwc / r))

        # Working capital days (retained for backward compatibility)
        a.ar_days = max(0.0, min(365.0, (b.get("ar", 0) / r) * 365.0))
        cogs = b.get("cogs", 0.0)
        a.inventory_days = max(0.0, min(365.0, (b.get("inventory", 0) / cogs) * 365.0)) if cogs > 0 else 0.0
        a.ap_days = max(0.0, min(365.0, (b.get("ap", 0) / cogs) * 365.0)) if cogs > 0 else 0.0

        # Residual working capital ratios
        a.other_ca_pct = max(0.0, min(0.50, b.get("other_ca", 0) / r))
        a.other_cl_pct = max(0.0, min(0.50, b.get("other_cl", 0) / r))

        # Reinvestment capex: use multi-year median capex/sales to smooth single-year outlier expansion spikes
        if historical is not None and not historical.empty and "capex" in historical.index and "revenue" in historical.index:
            c_s = historical.loc["capex"].dropna()
            r_s = historical.loc["revenue"].dropna()
            valid_cols = [col for col in c_s.index if col in r_s.index and r_s[col] > 0]
            if valid_cols:
                ratios = [abs(float(c_s[col])) / float(r_s[col]) for col in valid_cols]
                med_capex = float(np.median(ratios))
                a.capex_pct = max(0.02, min(0.25, med_capex))
            else:
                reported_capex = historical.iloc[:, -1].get("capex")
                if reported_capex is not None and pd.notna(reported_capex):
                    a.capex_pct = max(0.01, min(0.35, float(reported_capex) / r))

        # Revenue growth: anchor negative cyclical contractions to Indonesian economic baseline (3.5%)
        if historical is not None and not historical.empty and "revenue" in historical.index:
            s = historical.loc["revenue"].dropna()
            if len(s) >= 4 and s.iloc[-4] > 0 and s.iloc[-1] > 0:
                cagr3 = (float(s.iloc[-1]) / float(s.iloc[-4])) ** (1.0 / 3.0) - 1.0
                if cagr3 < 0:
                    # Cyclical commodity normalization: anchor baseline initial growth to Indonesian core economic baseline
                    a.growth = 0.035
                else:
                    a.growth = max(0.0, min(0.35, cagr3))
            elif len(s) >= 2 and s.iloc[-2] > 0 and s.iloc[-1] > 0:
                yoy = (float(s.iloc[-1]) / float(s.iloc[-2])) - 1.0
                a.growth = max(0.0, min(0.35, yoy)) if yoy >= 0 else 0.035

    # Depreciation rate on PPE
    if b.get("ppe", 0) > 0:
        a.depreciation_rate = max(0.01, min(0.50, b.get("da", 0) / b["ppe"]))

    # Loose ends per Damodaran Week 2 Slide 63
    minority = historical.iloc[:, -1].get("minority_interest") if historical is not None and not historical.empty else None
    if minority is not None and pd.notna(minority):
        a.other_claims = max(0.0, float(minority))

    nonop = historical.iloc[:, -1].get("nonoperating_assets") if historical is not None and not historical.empty else None
    if nonop is not None and pd.notna(nonop):
        a.nonoperating_assets = max(0.0, float(nonop))

    # Market-value capital structure weights per Damodaran Week 2 Slide 33 & 67
    tot_debt = b.get("short_debt", 0.0) + b.get("long_debt", 0.0)
    if company is not None and company.get("price") and company.get("shares"):
        mkt_cap = (float(company["price"]) * float(company["shares"])) / 1e9
        if mkt_cap > 0 and tot_debt >= 0:
            a.debt_weight = max(0.0, min(0.90, tot_debt / (tot_debt + mkt_cap)))

    # Borrowing cost from effective interest rate
    if tot_debt > 0 and b.get("interest", 0) > 0:
        eff_debt_rate = b["interest"] / tot_debt
        if 0.04 <= eff_debt_rate <= 0.20:
            a.debt_rate = round(eff_debt_rate, 4)

    # Blume's mean-reversion adjusted Beta with institutional floor (Damodaran CAPM alignment)
    if company is not None and company.get("beta") is not None:
        raw_beta = float(company["beta"])
        if math.isfinite(raw_beta):
            # Blume's adjustment reverts historical raw beta toward the market mean of 1.0:
            # Beta_adj = 0.67 * Beta_raw + 0.33 * 1.0
            # Institutional economic floor of 0.65 prevents negative/ultra-low betas from collapsing WACC below Rf
            blume_beta = 0.67 * raw_beta + 0.33
            a.beta = round(max(0.65, blume_beta), 4)

    # Year 5 mature growth: smooth convergence midpoint toward perpetual terminal growth
    a.mature_growth = round((a.growth + a.terminal_growth) / 2.0, 4)

    # Dynamic Growth-Deceleration & Competitive Convergence Model for Terminal ROIC
    # (Damodaran & McKinsey framework: Terminal ROIC fades below historical median toward WACC)
    hist_roic = compute_historical_roic(historical, b, tax_rate=a.tax_rate)
    g_init = max(0.02, a.growth)
    alpha = min(0.60, max(0.35, a.terminal_growth / g_init))
    converged_roic = alpha * hist_roic + (1.0 - alpha) * a.wacc
    # Enforce economic floor (terminal_growth + 1.5%) to guarantee reinvestment rate < 100%
    a.terminal_roic = round(max(a.terminal_growth + 0.015, converged_roic), 4)

    return a


def forecast(b, a, first_year, drivers=None):
    if not all(math.isfinite(float(b[k])) for k in BASE_FIELDS):
        raise ValueError("Every opening financial input must be a finite number.")
    if b["revenue"] <= 0:
        raise ValueError("Opening revenue must be positive.")
    if abs(base_check(b)) > max(0.01, abs(b["equity"]) * 1e-6):
        raise ValueError("Opening balance sheet does not balance. Correct the historical inputs first.")
    for name, value in asdict(a).items():
        if isinstance(value, (int, float)) and not math.isfinite(value):
            raise ValueError(f"Invalid assumption: {name}")
    if not (0 <= a.tax_rate < 1 and 0 <= a.dividend_payout <= 1 and 0 < a.gross_margin <= 1):
        raise ValueError("Check tax, payout, and gross margin assumptions.")
    if min(a.ar_days, a.inventory_days, a.ap_days, a.annual_repayment, a.depreciation_rate) < 0:
        raise ValueError("Days, repayments, and depreciation cannot be negative.")
    d = default_drivers(a, first_year) if drivers is None else drivers.copy()
    if len(d) != 5 or list(d["Year"]) != list(range(first_year, first_year + 5)):
        raise ValueError("The forecast needs exactly 5 consecutive annual periods.")
    if not np.isfinite(d.to_numpy(dtype=float)).all():
        raise ValueError("Annual assumptions cannot be blank or non-finite.")
    if (d["Growth %"] <= -100).any() or (d["Capex / sales %"] < 0).any():
        raise ValueError("Growth must exceed −100% and capex cannot be negative.")

    p = dict(b)
    p["nwc"] = b["ar"] + b["inventory"] + b["other_ca"] - b["ap"] - b["other_cl"]
    p["invested_capital"] = b["ppe"] + p["nwc"] + b["other_assets"]
    base_nwc_ratio = p["nwc"] / b["revenue"] if b["revenue"] > 0 else 0.10
    nwc_ratio = a.nwc_pct if a.nwc_pct is not None else base_nwc_ratio
    nol = 0.0

    result = []
    for _, row in d.iterrows():
        revenue = p["revenue"] * (1 + row["Growth %"] / 100)
        cogs = revenue * (1 - a.gross_margin)
        ebit = revenue * row["EBIT margin %"] / 100
        capex = revenue * row["Capex / sales %"] / 100
        da = min(p["ppe"] + capex, p["ppe"] * a.depreciation_rate)

        # Low-OpEx Bull Scenario Resilience:
        # If operating margin increases (cost efficiency), floor OpEx at 0 and absorb in COGS rather than crashing
        opex = revenue - cogs - da - ebit
        if opex < -1e-6:
            if ebit + da <= revenue * 0.999:
                opex = 0.0
                cogs = max(0.0, revenue - da - ebit)
            else:
                raise ValueError("Gross margin is too low for the requested EBIT margin and depreciation. Increase gross margin or lower EBIT margin.")

        opening_debt = p["short_debt"] + p["long_debt"]
        interest = opening_debt * a.debt_rate

        # Damodaran Operating Tax & Net Operating Loss (NOL) carryforward (Week 2 Slide 42)
        if ebit <= 0:
            taxable_ebit = 0.0
            nol += abs(ebit)
        else:
            taxable_ebit = max(0.0, ebit - nol)
            nol = max(0.0, nol - ebit)
        operating_tax = taxable_ebit * a.tax_rate
        nopat = ebit - operating_tax

        # Financial statement net income tax (interest deductible)
        tax = max(0.0, ebit - interest) * a.tax_rate
        net_income = ebit - interest - tax

        # Damodaran Non-Cash Working Capital as % of revenue (replaces granular turnover days)
        nwc = revenue * nwc_ratio
        delta_nwc = nwc - p["nwc"]

        scale = revenue / b["revenue"] if b["revenue"] > 0 else 1.0
        gross_ca = b["ar"] + b["inventory"] + b["other_ca"]
        gross_cl = b["ap"] + b["other_cl"]
        ar = b["ar"] * scale
        inventory = b["inventory"] * scale
        other_ca = b["other_ca"] * scale
        ap = b["ap"] * scale
        other_cl = b["other_cl"] * scale
        expected_nwc = gross_ca * scale - gross_cl * scale
        nwc_diff = nwc - expected_nwc
        if abs(nwc_diff) > 1e-9:
            tot_gross = gross_ca + gross_cl
            ca_weight = (gross_ca / tot_gross) if tot_gross > 0 else 0.5
            ar += nwc_diff * ca_weight
            ap -= nwc_diff * (1.0 - ca_weight)

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

        # Damodaran Reinvestment & Invested Capital (Week 2 Slide 41 & 48)
        reinvestment = (capex - da) + delta_nwc
        invested_capital = ppe + nwc + b["other_assets"]
        opening_ic = p["invested_capital"]
        roic = (nopat / opening_ic) if opening_ic > 0 else float("nan")

        f = dict(
            year=int(row["Year"]), revenue=revenue, cogs=cogs, opex=opex, da=da,
            ebitda=ebit + da, ebit=ebit, nopat=nopat, interest=interest, tax=tax, net_income=net_income,
            cash=cash, ar=ar, inventory=inventory, other_ca=other_ca, ppe=ppe,
            other_assets=b["other_assets"], ap=ap, other_cl=other_cl, short_debt=short_debt,
            long_debt=long_debt, other_liabilities=b["other_liabilities"], equity=equity,
            assets=assets, liabilities=liabilities, nwc=nwc, delta_nwc=delta_nwc,
            capex=capex, reinvestment=reinvestment, invested_capital=invested_capital, roic=roic,
            cfo=cfo, cfi=-capex, cff=funding - repayment - dividends,
            funding=funding, repayment=repayment, dividends=dividends,
            cash_change=cash - p["cash"], balance_check=assets - liabilities - equity,
            fcff=nopat + da - capex - delta_nwc
        )
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

    terminal_nopat = float(f.iloc[-1].ebit) * (1 - a.tax_rate) * (1 + g)
    if terminal_nopat <= 0:
        raise ValueError("Year 5 operating profit must be positive for this terminal-value method.")

    # Damodaran Sustainable Terminal Reinvestment = g / ROIC (Week 2 Slide 55)
    terminal_reinvestment_rate = (g / a.terminal_roic) if a.terminal_roic > 0 else 0.0
    terminal_fcff = terminal_nopat * (1 - terminal_reinvestment_rate)
    terminal_value = terminal_fcff / (w - g)
    pv_flows = sum(float(v) / (1 + w) ** i for i, v in enumerate(f.fcff, 1))
    pv_terminal = terminal_value / (1 + w) ** len(f)
    ev = pv_flows + pv_terminal

    # Damodaran Enterprise-to-Equity Value Bridge (Week 2 Slide 63)
    eq = ev + b["cash"] + a.nonoperating_assets - b["short_debt"] - b["long_debt"] - a.other_claims
    y_exit_ebitda = float(f.iloc[-1].ebitda)

    return dict(
        wacc=w, terminal_nopat=terminal_nopat, terminal_reinvestment_rate=terminal_reinvestment_rate,
        terminal_fcff=terminal_fcff, terminal_value=terminal_value,
        pv_flows=pv_flows, pv_terminal=pv_terminal, enterprise_value=ev,
        equity_value=eq, price=eq / shares, terminal_share=pv_terminal / ev if ev else 0,
        implied_exit_ev_ebitda=(terminal_value / y_exit_ebitda) if y_exit_ebitda > 0 else float("nan")
    )


def sensitivity(f, b, a, shares):
    from dataclasses import replace
    ws = [a.wacc + x for x in (-.02, -.01, 0, .01, .02)]
    gs = [max(0, a.terminal_growth + x) for x in (-.01, -.005, 0, .005, .01)]
    grid = []
    for w in ws:
        vals = []
        for g in gs:
            try:
                vals.append(dcf(f, b, replace(a, wacc_override=w, terminal_growth=g), shares)["price"])
            except ValueError:
                vals.append(float("nan"))
        grid.append(vals)
    return pd.DataFrame(grid, index=[f"{w:.2%}" for w in ws], columns=[f"{g:.2%}" for g in gs])


def relative_values(peers, target, cash, debt, shares, other_claims=0, nonoperating_assets=0):
    """Peer rows and target denominators must use the same annual period basis.
    Enterprise multiples exclude negative EV and non-positive denominators.
    Aligned with Damodaran Week 4 Slide 7 & 25 (EV/Rev, EV/EBITDA, EV/EBIT, P/E, P/BV).
    """
    if shares <= 0:
        raise ValueError("Shares must be positive.")
    rows = []
    multiples_spec = [
        ("EV / EBITDA", "ebitda", "ev"),
        ("EV / EBIT", "ebit", "ev"),
        ("P / E", "net_income", "market_cap"),
    ]
    # Add P/BV if book_equity is provided in target and peers
    if "book_equity" in target and target["book_equity"] is not None and target["book_equity"] > 0:
        multiples_spec.append(("P / BV", "book_equity", "market_cap"))

    for label, metric, numerator in multiples_spec:
        multiples = []
        for p in peers:
            den, num = p.get(metric), p.get(numerator)
            if den is not None and num is not None and math.isfinite(den) and math.isfinite(num) and den > 0 and num > 0:
                multiples.append(num / den)
        cases = [
            ("Lower quartile", float(np.percentile(multiples, 25)) if multiples else float("nan")),
            ("Median", float(np.percentile(multiples, 50)) if multiples else float("nan")),
            ("Harmonic mean", float(len(multiples) / np.sum([1.0 / m for m in multiples])) if multiples and all(m > 0 for m in multiples) else float("nan")),
            ("Upper quartile", float(np.percentile(multiples, 75)) if multiples else float("nan")),
        ]
        for name, mult in cases:
            denominator = target.get(metric)
            value = mult * denominator if denominator is not None and denominator > 0 else float("nan")
            equity = value + cash + nonoperating_assets - debt - other_claims if numerator == "ev" else value
            rows.append({"Multiple": label, "Case": name, "Peers used": len(multiples), "Peer multiple": mult, "Implied price (IDR)": equity / shares})
    return pd.DataFrame(rows)


def composite_relative_value(
    relative_df, 
    metrics=("EV / EBITDA", "EV / EBIT", "P / E", "P / BV"), 
    case="Median", 
    weights=None, 
    min_peers=2, 
    return_breakdown=False
):
    """Calculates the composite implied price from peer multiples (defaults to Median, supports Harmonic mean).
    - Requires at least `min_peers` (default 2) valid peer multiples per metric to be ELIGIBLE.
    - If `weights` dict is provided (e.g. {'EV / EBITDA': 0.4, 'EV / EBIT': 0.2, 'P / E': 0.2, 'P / BV': 0.2}),
      computes the normalized weighted average implied price over eligible multiples.
    - If return_breakdown is True, returns (composite_price, breakdown_dict).
    """
    if relative_df is None or relative_df.empty:
        return (float("nan"), {}) if return_breakdown else float("nan")

    case_rows = relative_df[relative_df["Case"] == case]
    breakdown = {}
    eligible_prices = []
    eligible_weights = []

    for m in metrics:
        subset = case_rows[case_rows["Multiple"] == m]
        if not subset.empty:
            row = subset.iloc[0]
            price = row["Implied price (IDR)"]
            peers_count = int(row["Peers used"]) if pd.notna(row.get("Peers used")) else 0
            multiple_val = row["Peer multiple"]
            is_valid_price = pd.notna(price) and math.isfinite(price) and price > 0
            is_eligible = is_valid_price and peers_count >= min_peers

            raw_w = 0.0
            if weights and m in weights:
                raw_w = max(0.0, float(weights[m]))
            else:
                raw_w = 1.0 / len(metrics)

            breakdown[m] = {
                "multiple_name": m,
                "peer_multiple": multiple_val,
                "implied_price": price if is_valid_price else float("nan"),
                "peers_used": peers_count,
                "eligible": is_eligible,
                "configured_weight": raw_w,
                "effective_weight": 0.0,
            }

            if is_eligible:
                eligible_prices.append(price)
                eligible_weights.append(raw_w)
        else:
            breakdown[m] = {
                "multiple_name": m,
                "peer_multiple": float("nan"),
                "implied_price": float("nan"),
                "peers_used": 0,
                "eligible": False,
                "configured_weight": 0.0,
                "effective_weight": 0.0,
            }

    if not eligible_prices:
        comp_price = float("nan")
    else:
        tot_w = sum(eligible_weights)
        if tot_w > 0:
            norm_weights = [w / tot_w for w in eligible_weights]
            comp_price = float(np.sum(np.array(eligible_prices) * np.array(norm_weights)))
            idx = 0
            for m in metrics:
                if breakdown[m]["eligible"]:
                    breakdown[m]["effective_weight"] = norm_weights[idx]
                    idx += 1
        else:
            comp_price = float(np.mean(eligible_prices))
            eq_w = 1.0 / len(eligible_prices)
            for m in metrics:
                if breakdown[m]["eligible"]:
                    breakdown[m]["effective_weight"] = eq_w

    if return_breakdown:
        return comp_price, breakdown
    return comp_price


def get_multiple_exclusion_details(peers):
    """Analyzes active peers and identifies specific reasons why peers were excluded
    from each relative valuation multiple (e.g. negative operating profit, net loss).
    """
    multiples_spec = {
        "EV / EBITDA": ("ebitda", "ev", "EBITDA"),
        "EV / EBIT": ("ebit", "ev", "operating income (EBIT)"),
        "P / E": ("net_income", "market_cap", "net income"),
        "P / BV": ("book_equity", "market_cap", "book equity"),
    }

    details = {}
    for m_name, (den_key, num_key, desc) in multiples_spec.items():
        excluded_peers = []
        for p in (peers or []):
            den = p.get(den_key)
            num = p.get(num_key)
            sym = p.get("ticker", "").replace(".JK", "")

            if den is None or not math.isfinite(den) or den <= 0:
                if den is not None and math.isfinite(den) and den < 0:
                    val_str = f"-Rp {abs(den):,.0f} bn" if abs(den) < 1000 else f"-Rp {abs(den)/1000:,.1f} T"
                    excluded_peers.append(f"{sym} (negative {desc}: {val_str})")
                elif den == 0:
                    excluded_peers.append(f"{sym} (zero {desc})")
                else:
                    excluded_peers.append(f"{sym} (missing {desc})")
            elif num is None or not math.isfinite(num) or num <= 0:
                excluded_peers.append(f"{sym} (non-positive enterprise/market value)")

        details[m_name] = excluded_peers
    return details


def explain_peer_selection(target_profile, peer_record):
    """Generates an intuitive, professional 'Why Selected?' explanation for a peer:
    - Confirms sub-industry match or cross-industry context
    - Compares EBITDA margin against target
    - Compares Debt-to-Equity (DER) against target
    - Mentions financial similarity distance
    """
    target_ind = (target_profile.get("industry") or "").strip()
    peer_ind = (peer_record.get("industry") or "").strip()
    target_margin = target_profile.get("ebitda_margin")
    peer_margin = peer_record.get("ebitda_margin")
    target_der = target_profile.get("der")
    peer_der = peer_record.get("der")
    dist = peer_record.get("similarity_distance")

    reasons = []
    if target_ind and peer_ind and target_ind.lower() == peer_ind.lower():
        reasons.append(f"Direct sub-industry peer ({target_ind})")
    elif peer_ind:
        reasons.append(f"Related industry peer ({peer_ind})")

    if target_margin is not None and peer_margin is not None:
        margin_diff = abs(peer_margin - target_margin)
        if margin_diff <= 0.05:
            reasons.append(f"closely aligned EBITDA margin ({peer_margin:.1%} vs target {target_margin:.1%})")
        else:
            reasons.append(f"EBITDA margin {peer_margin:.1%} (target {target_margin:.1%})")

    if target_der is not None and peer_der is not None:
        der_diff = abs(peer_der - target_der)
        if der_diff <= 0.3:
            reasons.append(f"comparable leverage (DER {peer_der:.2f}x vs {target_der:.2f}x)")
        else:
            reasons.append(f"DER {peer_der:.2f}x (target {target_der:.2f}x)")

    score = peer_record.get("similarity_score")
    conf = peer_record.get("confidence_level")
    if score is not None:
        reasons.append(f"similarity score {score}/100 ({conf.lower()} confidence)" if conf else f"similarity score {score}/100")
    elif dist is not None:
        reasons.append(f"similarity distance {dist:.2f}")

    return "; ".join(reasons) if reasons else "Industry comparable peer candidate."


def blended_valuation(dcf_price, rel_price, dcf_weight=0.75, rel_weight=0.25):
    """Blends DCF and Relative Valuation prices according to Valuation Policy weights."""
    valid_dcf = pd.notna(dcf_price) and math.isfinite(dcf_price)
    has_rel = pd.notna(rel_price) and math.isfinite(rel_price) and rel_price > 0

    if valid_dcf:
        # Equity limited liability: intrinsic equity per share cannot fall below 0 in public equity markets
        eff_dcf = max(0.0, float(dcf_price))
        if has_rel:
            total_w = dcf_weight + rel_weight
            if total_w <= 0:
                return eff_dcf
            return float((eff_dcf * dcf_weight + rel_price * rel_weight) / total_w)
        return eff_dcf
    elif has_rel:
        return float(rel_price)
    return float("nan")


def evaluate_approach_weights(target_profile, peer_records, default_dcf_weight=0.75, default_rel_weight=0.25):
    """Evaluates valuation approach weighting based on:
    - Rule 1 (Intrinsic Anchor): DCF (FCFF) is assigned primary emphasis because it measures
      intrinsic cash generation, balance sheet solvency, and reinvestment efficiency independently of market sentiment.
    - Rule 2 (Peer Quality Calibration): Relative Valuation is included as a secondary market cross-check
      only if at least 2 peers in the same sub-industry meet financial similarity thresholds.
      If fewer than 2 comparable peers are available, the model shifts 100% of weight to DCF.
    """
    valid_peers = [p for p in peer_records if p.get("ev") and p.get("ev") > 0] if peer_records else []

    if len(valid_peers) >= 2:
        target_margin = target_profile.get("ebitda_margin")
        target_der = target_profile.get("der")
        close_peers = 0
        for p in valid_peers:
            pm = p.get("ebitda_margin")
            pder = p.get("der")
            if pm is not None and target_margin is not None and abs(pm - target_margin) <= 0.15:
                if pder is not None and target_der is not None and abs(pder - target_der) <= 1.0:
                    close_peers += 1

        peer_quality = "High" if close_peers >= 2 else "Moderate"
        dcf_w = default_dcf_weight
        rel_w = default_rel_weight
        rationale = (
            f"Rule 1 & Rule 2 Active: Intrinsic DCF is weighted at {dcf_w:.0%} as the primary fundamental anchor. "
            f"Relative Valuation provides a {rel_w:.0%} secondary market cross-check ({peer_quality} peer quality, "
            f"{len(valid_peers)} active peers in same sub-industry)."
        )
        return dict(dcf_weight=dcf_w, rel_weight=rel_w, quality=peer_quality, rationale=rationale, peers_valid=True)
    else:
        dcf_w = 1.0
        rel_w = 0.0
        rationale = (
            f"Rule 1 Active (100% Intrinsic DCF): Insufficient comparable peers loaded (< 2 peers, currently {len(valid_peers)}). "
            f"Under Rule 2 (Peer Quality Calibration), relative valuation is suspended to avoid pricing distortion from a single or absent peer."
        )
        return dict(dcf_weight=dcf_w, rel_weight=rel_w, quality="Insufficient Peers", rationale=rationale, peers_valid=False)


def investment_recommendation(reference_price, blended_price, hurdle_rate=0.15):
    """Generates an institutional recommendation and margin of safety analysis:
    - BUY / OVERWEIGHT: Implied upside > +15%
    - HOLD / NEUTRAL: Implied upside between -15% and +15%
    - SELL / UNDERWEIGHT: Implied upside < -15%
    - Distressed Balance Sheet: blended_price <= 0 due to debt exceeding enterprise value
    """
    if not reference_price or not (reference_price > 0):
        return dict(
            rating="DATA PENDING",
            upside=0.0,
            margin_of_safety=0.0,
            color="#8c9e99",
            summary="Reference market price pending review of inputs."
        )

    if blended_price is None or not math.isfinite(blended_price):
        return dict(
            rating="DATA PENDING",
            upside=0.0,
            margin_of_safety=0.0,
            color="#8c9e99",
            summary="Fair value calculation pending review of inputs."
        )

    if blended_price <= 0:
        return dict(
            rating="NOT ELIGIBLE",
            upside=0.0,
            margin_of_safety=0.0,
            color="#6c757d",
            summary=(
                f"Ineligible for Valuation Model: Operating enterprise value is insufficient to cover net debt "
                f"(fundamental equity value is underwater at Rp {blended_price:,.2f}). "
                f"Standard going-concern non-financial DCF is not applicable to financially distressed capital structures."
            )
        )

    upside = (blended_price / reference_price) - 1.0
    margin_of_safety = 1.0 - (reference_price / blended_price) if blended_price > reference_price else upside

    if upside >= hurdle_rate:
        rating = "BUY / OVERWEIGHT"
        color = "#087f69"
        summary = (
            f"Strong valuation support: Blended fair value (Rp {blended_price:,.0f}) trades at a {upside:+.1%} premium "
            f"to market price (Rp {reference_price:,.0f}), exceeding the {hurdle_rate:.0%} hurdle margin of safety."
        )
    elif upside <= -hurdle_rate:
        rating = "SELL / UNDERWEIGHT"
        color = "#c23b22"
        summary = (
            f"Valuation headwind: Reference market price (Rp {reference_price:,.0f}) trades at a {abs(upside):.1%} premium "
            f"over blended fair value (Rp {blended_price:,.0f}), indicating potential downside risk."
        )
    else:
        rating = "HOLD / NEUTRAL"
        color = "#d9822b"
        summary = (
            f"Fairly valued: Implied upside/downside of {upside:+.1%} sits within the neutral [−{hurdle_rate:.0%}, +{hurdle_rate:.0%}] "
            f"valuation band. Risk/reward profile is balanced at current market levels."
        )

    return dict(
        rating=rating,
        upside=upside,
        margin_of_safety=margin_of_safety,
        color=color,
        summary=summary
    )
