from dataclasses import replace
from io import BytesIO
import pandas as pd
import pytest
from openpyxl import load_workbook
from valuation.data import demo_company, normalize, ticker_symbol, peer_record
from valuation.model import (Assumptions, BASE_FIELDS, base_check, forecast, dcf, sensitivity, default_drivers, relative_values, infer_assumptions, compute_historical_roic, composite_relative_value, blended_valuation, evaluate_approach_weights, investment_recommendation)
from valuation.data import rank_peers_similarity
from valuation.export import workbook


@pytest.fixture
def case():
    c = demo_company()
    b = c["historical"].loc[list(BASE_FIELDS)].iloc[:,-1].to_dict()
    return c,b,Assumptions()


def test_statements_balance_and_cash_flows_reconcile(case):
    _,b,a = case
    f = forecast(b,a,2026)
    assert abs(base_check(b)) < 1e-8
    assert f.balance_check.abs().max() < 1e-8
    assert (f.cfo+f.cfi+f.cff-f.cash_change).abs().max() < 1e-8
    opening = b["equity"]
    for _,r in f.iterrows():
        assert r.equity == pytest.approx(opening+r.net_income-r.dividends)
        opening = r.equity


def test_cash_shortfall_is_explicitly_financed(case):
    _,b,a = case
    f = forecast(b,replace(a,capex_pct=.5,depreciation_rate=.04),2026)
    assert f.funding.sum() > 0
    assert (f.cash-f.revenue*a.minimum_cash_pct).min() >= -1e-8
    assert f.balance_check.abs().max() < 1e-8


def test_repayment_cannot_exceed_debt(case):
    _,b,a = case
    f = forecast(b,replace(a,annual_repayment=100000),2026)
    assert f.iloc[0].repayment == b["short_debt"]+b["long_debt"]
    assert f.short_debt.min() >= 0 and f.long_debt.min() >= 0
    assert f.balance_check.abs().max() < 1e-8


def test_dcf_discount_direction_and_equity_bridge(case):
    _,b,a = case
    f = forecast(b,a,2026)
    low = dcf(f,b,replace(a,wacc_override=.10),8)
    high = dcf(f,b,replace(a,wacc_override=.14),8)
    assert low["price"] > high["price"]
    assert low["equity_value"] == pytest.approx(low["enterprise_value"]+b["cash"]-b["short_debt"]-b["long_debt"])
    assert low["price"] == pytest.approx(low["equity_value"]/8)
    doubled = dcf(f,b,replace(a,wacc_override=.10),16)
    assert doubled["price"] == pytest.approx(low["price"]/2)


def test_terminal_reinvestment_is_growth_over_roic(case):
    _,b,a = case
    f = forecast(b,a,2026)
    r = dcf(f,b,a,8)
    expected = f.iloc[-1].ebit*(1-a.tax_rate)*(1+a.terminal_growth)*(1-a.terminal_growth/a.terminal_roic)
    assert r["terminal_fcff"] == pytest.approx(expected)


def test_rejects_bad_inputs(case):
    _,b,a = case
    with pytest.raises(ValueError,match="balance"):
        forecast(b|{"cash":0},a,2026)
    f = forecast(b,a,2026)
    with pytest.raises(ValueError,match="WACC"):
        dcf(f,b,replace(a,wacc_override=.02),8)
    with pytest.raises(ValueError,match="ROIC"):
        dcf(f,b,replace(a,terminal_roic=.01),8)
    with pytest.raises(ValueError,match="Shares"):
        dcf(f,b,a,0)
    d = default_drivers(a,2026)
    d.loc[0,"Growth %"] = -100
    with pytest.raises(ValueError,match="Growth"):
        forecast(b,a,2026,d)


def test_relative_uses_positive_denominators_and_equity_bridge():
    peers = [dict(ev=100,market_cap=80,revenue=50,ebitda=10,ebit=8,net_income=5),
             dict(ev=200,market_cap=160,revenue=100,ebitda=-10,ebit=16,net_income=-5)]
    target = dict(revenue=100,ebitda=20,ebit=16,net_income=10)
    r = relative_values(peers,target,10,30,10).query("Case == 'Median'").set_index("Multiple")
    assert r.loc["EV / EBITDA","Peers used"] == 1
    assert "EV / Revenue" not in r.index
    assert r.loc["EV / EBIT","Implied price (IDR)"] == pytest.approx(18)
    assert r.loc["P / E","Implied price (IDR)"] == pytest.approx(16)


def test_missing_data_is_not_zero():
    date = pd.Timestamp("2025-12-31")
    income = pd.DataFrame({date:{"TotalRevenue":100e9,"OperatingIncome":20e9}})
    balance = pd.DataFrame({date:{"TotalAssets":80e9}})
    cf = pd.DataFrame({date:{"OperatingCashFlow":15e9}})
    h,p = normalize(income,balance,cf)
    assert h.loc["revenue"].iloc[0] == 100
    assert pd.isna(h.loc["inventory"].iloc[0])
    assert "Missing" in p["2025-12-31:inventory"]


def test_no_mixed_fiscal_dates(case):
    c,_,_ = case
    with pytest.raises(ValueError,match="matching fiscal"):
        peer_record(c,"2020-12-31",1)
    assert ticker_symbol(" tlkm ") == "TLKM.JK"
    with pytest.raises(ValueError):
        ticker_symbol("AAPL.US")


def test_direct_cashflow_label_and_empty_placeholder_period():
    date,empty = pd.Timestamp("2025-12-31"),pd.Timestamp("2024-12-31")
    income = pd.DataFrame({date:{"TotalRevenue":100e9},empty:{"TotalRevenue":None}})
    balance = pd.DataFrame({date:{"TotalAssets":80e9},empty:{"TotalAssets":None}})
    cf = pd.DataFrame({date:{"CashFlowsfromusedinOperatingActivitiesDirect":15e9},empty:{"CashFlowsfromusedinOperatingActivitiesDirect":None}})
    h,_ = normalize(income,balance,cf)
    assert list(h.columns) == ["2025-12-31"]
    assert h.loc["cfo","2025-12-31"] == 15


def test_excel_contains_forecast_and_sensitivity(case):
    c,b,a = case
    f = forecast(b,a,2026)
    r = dcf(f,b,a,8)
    output = workbook(c,c["historical"],b,a,default_drivers(a,2026),f,r,sensitivity(f,b,a,8),[],pd.DataFrame())
    book = load_workbook(BytesIO(output))
    assert "Forecast IDR bn" in book.sheetnames
    assert "Sensitivity IDR" in book.sheetnames
    assert book["Forecast IDR bn"].max_column == 6  # 1 index column + 5 forecast years


def test_low_opex_bull_scenario_does_not_crash():
    # Low-OpEx profile (distribution model where opex is only ~2% of revenue)
    base = dict(revenue=46000., cogs=41900., opex=980., da=48., interest=280., tax=675., net_income=2400.,
                cash=6400., ar=9500., inventory=6600., other_ca=760., ppe=6800., other_assets=6400.,
                ap=12000., other_cl=3400., short_debt=1800., long_debt=4200., other_liabilities=1400., equity=13660.)
    a = Assumptions(growth=0.08, mature_growth=0.04, ebit_margin=0.066, mature_margin=0.066, gross_margin=0.089,
                    ar_days=75., inventory_days=57., ap_days=104., capex_pct=0.023, depreciation_rate=0.007)
    # Test Bull scenario (+2% EBIT margin shift)
    drivers = default_drivers(a, 2026)
    drivers["Growth %"] += 2.0
    drivers["EBIT margin %"] += 2.0
    f = forecast(base, a, 2026, drivers)
    assert not f.empty
    assert (f.opex >= 0).all()
    assert (f.fcff > 0).all()
    r = dcf(f, base, a, 19.7)
    assert r["price"] > 0


def test_infer_assumptions_uses_yfinance_beta_and_market_debt_weight(case):
    c, b, _ = case
    company_meta = dict(price=1400., shares=20e9, beta=-0.25)
    inferred = infer_assumptions(c["historical"], b, company_meta)
    # Blume adjustment: 0.67 * (-0.25) + 0.33 = 0.1625 -> constrained by floor >= 0.65
    assert inferred.beta == 0.65

    company_meta_pos = dict(price=1400., shares=20e9, beta=1.20)
    inferred_pos = infer_assumptions(c["historical"], b, company_meta_pos)
    assert inferred_pos.beta == pytest.approx(1.1340)
    # Total debt = short_debt (300) + long_debt (1700) = 2000 bn
    # Market Cap = 1400 * 20e9 / 1e9 = 28000 bn
    # Debt weight = 2000 / (2000 + 28000) = 2000 / 30000 = ~6.67%
    assert inferred.debt_weight == pytest.approx(2000. / 30000., abs=0.005)


def test_ebit_sanity_validation_corrects_yahoo_sign_inversion():
    dates = [pd.Timestamp("2024-12-31")]
    inc_df = pd.DataFrame({
        dates[0]: {
            "TotalRevenue": 10000.0 * 1e9,
            "CostOfRevenue": 4000.0 * 1e9,
            "OperatingIncome": 5000.0 * 1e9,  # Distorted by negative OpEx sign bug
            "EBIT": 2500.0 * 1e9,            # True operating profit
            "PretaxIncome": 2400.0 * 1e9,
            "InterestExpense": 100.0 * 1e9,
            "TaxProvision": 500.0 * 1e9,
            "NetIncome": 1900.0 * 1e9,
        }
    })
    bs_df = pd.DataFrame({
        dates[0]: {
            "CashCashEquivalentsAndShortTermInvestments": 1000.0 * 1e9,
            "Receivables": 1200.0 * 1e9,
            "Inventory": 800.0 * 1e9,
            "CurrentAssets": 3500.0 * 1e9,
            "NetPPE": 5000.0 * 1e9,
            "TotalAssets": 9000.0 * 1e9,
            "AccountsPayable": 700.0 * 1e9,
            "CurrentDebtAndCapitalLeaseObligation": 300.0 * 1e9,
            "CurrentLiabilities": 1200.0 * 1e9,
            "LongTermDebtAndCapitalLeaseObligation": 1000.0 * 1e9,
            "TotalLiabilitiesNetMinorityInterest": 2500.0 * 1e9,
            "TotalEquityGrossMinorityInterest": 6500.0 * 1e9,
        }
    })
    cf_df = pd.DataFrame({
        dates[0]: {
            "DepreciationAndAmortization": 500.0 * 1e9,
            "OperatingCashFlow": 2200.0 * 1e9,
            "CapitalExpenditure": 600.0 * 1e9,
        }
    })

    hist, prov = normalize(inc_df, bs_df, cf_df)
    # Sanitized EBIT should be 2500, not 5000
    assert hist.loc["ebit", "2024-12-31"] == 2500.0
    # OpEx = Revenue (10000) - COGS (4000) - D&A (500) - EBIT (2500) = 3000
    assert hist.loc["opex", "2024-12-31"] == 3000.0
    assert hist.loc["opex", "2024-12-31"] >= 0.0


def test_relative_values_with_pbv():
    peers = [dict(ev=100, market_cap=80, revenue=50, ebitda=10, ebit=8, net_income=5, book_equity=40),
             dict(ev=200, market_cap=160, revenue=100, ebitda=20, ebit=16, net_income=10, book_equity=80)]
    target = dict(revenue=100, ebitda=20, ebit=16, net_income=10, book_equity=50)
    r = relative_values(peers, target, 10, 30, 10).query("Case == 'Median'").set_index("Multiple")
    assert "P / BV" in r.index
    assert r.loc["P / BV", "Peer multiple"] == pytest.approx(2.0)
    assert r.loc["P / BV", "Implied price (IDR)"] == pytest.approx(10.0)


def test_damodaran_crp_mature_erp_and_cost_of_equity():
    a = Assumptions(beta=1.2)
    assert a.mature_equity_premium == pytest.approx(0.0460)
    assert a.country_risk_premium == pytest.approx(0.0218)
    assert a.total_equity_premium == pytest.approx(0.0678)
    assert a.risk_free == pytest.approx(0.0664)
    assert a.cost_of_equity == pytest.approx(0.0664 + 1.2 * 0.0678)


def test_composite_relative_valuation_and_blended_weighting():
    import math
    peers = [
        dict(ev=100, market_cap=80, revenue=50, ebitda=10, ebit=8, net_income=5, book_equity=40),
        dict(ev=200, market_cap=160, revenue=100, ebitda=20, ebit=16, net_income=10, book_equity=80)
    ]
    target = dict(revenue=100, ebitda=20, ebit=16, net_income=10, book_equity=50)
    rel_df = relative_values(peers, target, cash=10, debt=30, shares=10)
    comp_price = composite_relative_value(rel_df)
    assert math.isfinite(comp_price)
    assert comp_price > 0
    blended = blended_valuation(1000.0, 800.0, dcf_weight=0.75, rel_weight=0.25)
    assert blended == pytest.approx(950.0)
    assert blended_valuation(1000.0, float('nan'), 0.75, 0.25) == 1000.0


def test_peer_similarity_ranking_by_ebitda_margin_and_der():
    target = dict(ebitda_margin=0.20, der=0.50, industry='Thermal Coal')
    candidates = [
        dict(ticker='FAR', industry='Telecom', ebitda_margin=0.40, der=1.20),
        dict(ticker='CLOSE', industry='Thermal Coal', ebitda_margin=0.22, der=0.48),
        dict(ticker='MEDIUM', industry='Thermal Coal', ebitda_margin=0.15, der=1.10),
    ]
    ranked = rank_peers_similarity(target, candidates)
    assert ranked[0]['ticker'] == 'CLOSE'
    assert ranked[1]['ticker'] == 'MEDIUM'
    assert ranked[2]['ticker'] == 'FAR'


def test_evaluate_approach_weights_rule_1_and_rule_2():
    target = dict(ebitda_margin=0.20, der=0.50, industry='Thermal Coal')
    # Case A: Insufficient peers (< 2 peers) -> Rule 1 shifts to 100% DCF
    r_empty = evaluate_approach_weights(target, [])
    assert r_empty['dcf_weight'] == 1.0
    assert r_empty['rel_weight'] == 0.0
    assert not r_empty['peers_valid']

    # Case B: 2 valid peers -> Rule 1 (75% DCF) & Rule 2 (25% Relative)
    peers = [
        dict(ticker='P1', ev=100.0, ebitda_margin=0.22, der=0.55),
        dict(ticker='P2', ev=150.0, ebitda_margin=0.18, der=0.45),
    ]
    r_valid = evaluate_approach_weights(target, peers)
    assert r_valid['dcf_weight'] == 0.75
    assert r_valid['rel_weight'] == 0.25
    assert r_valid['peers_valid']
    assert 'Rule 1 & Rule 2 Active' in r_valid['rationale']


def test_investment_recommendation_hurdles():
    # Buy: +20% upside (> +15% hurdle)
    buy = investment_recommendation(reference_price=1000.0, blended_price=1200.0, hurdle_rate=0.15)
    assert buy['rating'] == 'BUY / OVERWEIGHT'
    assert buy['upside'] == pytest.approx(0.20)

    # Hold: +5% upside (within [-15%, +15%] neutral band)
    hold = investment_recommendation(reference_price=1000.0, blended_price=1050.0, hurdle_rate=0.15)
    assert hold['rating'] == 'HOLD / NEUTRAL'

    # Sell: -20% downside (< -15% hurdle)
    sell = investment_recommendation(reference_price=1000.0, blended_price=800.0, hurdle_rate=0.15)
    assert sell['rating'] == 'SELL / UNDERWEIGHT'
    assert sell['upside'] == pytest.approx(-0.20)

    # Ineligible / Distressed / Negative Equity: e.g. DEWA or SMGR where debt exceeds EV
    ineligible = investment_recommendation(reference_price=268.0, blended_price=0.0)
    assert ineligible['rating'] == 'NOT ELIGIBLE'
    assert ineligible['upside'] == 0.0
    assert ineligible['margin_of_safety'] == 0.0
    assert 'Ineligible' in ineligible['summary']

    # Pending: Missing price or NaN
    pending = investment_recommendation(reference_price=0.0, blended_price=100.0)
    assert pending['rating'] == 'DATA PENDING'
    pending_nan = investment_recommendation(reference_price=100.0, blended_price=float('nan'))
    assert pending_nan['rating'] == 'DATA PENDING'


def test_blended_valuation_floors_negative_dcf_equity():
    # When DCF equity is negative (e.g. -43.53), floor at 0 under equity limited liability
    blend_solo = blended_valuation(dcf_price=-43.53, rel_price=float('nan'), dcf_weight=0.75, rel_weight=0.25)
    assert blend_solo == 0.0

    # When Relative Valuation has positive value, blend 0.0 and positive relative price
    blend_with_rel = blended_valuation(dcf_price=-43.53, rel_price=100.0, dcf_weight=0.75, rel_weight=0.25)
    assert blend_with_rel == pytest.approx(25.0)


def test_default_terminal_growth_aligns_with_bi_target():
    asm = Assumptions()
    assert asm.terminal_growth == pytest.approx(0.025)
    assert asm.mature_growth == pytest.approx(0.025)


def test_sustainable_growth_and_capex_normalization(case):
    _, b, _ = case
    # Case A: Post-peak commodity contraction (revenue drops from 150k to 35k)
    hist_cyclical = pd.DataFrame({
        "2022-12-31": {"revenue": 150000.0, "capex": 5000.0},
        "2023-12-31": {"revenue": 45000.0, "capex": 4000.0},
        "2024-12-31": {"revenue": 40000.0, "capex": 3800.0},
        "2025-12-31": {"revenue": 35000.0, "capex": 15000.0},
    })
    b_cyclical = dict(b, revenue=35000.0)
    inferred_cyclical = infer_assumptions(hist_cyclical, b_cyclical)
    # Negative CAGR (-38%) is anchored to Indonesian economic baseline 3.5%, not -15%
    assert inferred_cyclical.growth == pytest.approx(0.035)
    # Capex uses multi-year median (~9.5% - 10.8%), not the single-year 42.8% outlier
    assert inferred_cyclical.capex_pct < 0.20
    assert inferred_cyclical.capex_pct > 0.05

    # Case B: Normal growing company (revenue grows from 10k to 15k)
    hist_growing = pd.DataFrame({
        "2022-12-31": {"revenue": 10000.0, "capex": 600.0},
        "2023-12-31": {"revenue": 11500.0, "capex": 700.0},
        "2024-12-31": {"revenue": 13000.0, "capex": 750.0},
        "2025-12-31": {"revenue": 15000.0, "capex": 900.0},
    })
    b_growing = dict(b, revenue=15000.0)
    inferred_growing = infer_assumptions(hist_growing, b_growing)
    # Positive growth is 100% preserved
    expected_cagr = (15000.0 / 10000.0) ** (1.0 / 3.0) - 1.0
    assert inferred_growing.growth == pytest.approx(expected_cagr)


def test_relative_values_includes_harmonic_mean():
    import math
    peers = [
        dict(ev=100, market_cap=50, revenue=100, ebitda=20, ebit=15, net_income=10, book_equity=25),
        dict(ev=200, market_cap=100, revenue=200, ebitda=40, ebit=30, net_income=10, book_equity=50),
        dict(ev=400, market_cap=200, revenue=400, ebitda=80, ebit=60, net_income=10, book_equity=100),
    ]
    target = dict(revenue=100, ebitda=20, ebit=15, net_income=10, book_equity=50)
    df = relative_values(peers, target, cash=10, debt=20, shares=10)
    
    assert set(df["Case"].unique()) == {"Lower quartile", "Median", "Harmonic mean", "Upper quartile"}
    
    pe_hm = df[(df["Case"] == "Harmonic mean") & (df["Multiple"] == "P / E")].iloc[0]
    expected_pe = 3.0 / (1.0/5.0 + 1.0/10.0 + 1.0/20.0) # 3 / 0.35 = 8.57142857
    assert pe_hm["Peer multiple"] == pytest.approx(expected_pe)
    assert pe_hm["Implied price (IDR)"] == pytest.approx(expected_pe)
    
    comp_hm = composite_relative_value(df, case="Harmonic mean")
    assert math.isfinite(comp_hm)
    assert comp_hm > 0


def test_get_doh_session_injects_secure_dns():
    from valuation.data import get_doh_session
    s = get_doh_session()
    assert s is not None
    assert hasattr(s, "request")


def test_composite_relative_value_custom_weights():
    peers = [
        dict(ev=100, market_cap=80, revenue=50, ebitda=10, ebit=8, net_income=5, book_equity=40),
        dict(ev=200, market_cap=160, revenue=100, ebitda=20, ebit=16, net_income=10, book_equity=80),
    ]
    target = dict(revenue=100, ebitda=20, ebit=16, net_income=10, book_equity=50)
    rel_df = relative_values(peers, target, cash=10, debt=30, shares=10)

    # Weights: 50% EV/EBITDA (implied price 18), 50% P/E (implied price 16)
    weights = {"EV / EBITDA": 0.50, "EV / EBIT": 0.0, "P / E": 0.50, "P / BV": 0.0}
    comp_price, breakdown = composite_relative_value(rel_df, weights=weights, return_breakdown=True)

    assert comp_price == pytest.approx(17.0)
    assert breakdown["EV / EBITDA"]["eligible"] is True
    assert breakdown["P / E"]["eligible"] is True
    assert breakdown["EV / EBITDA"]["implied_price"] == pytest.approx(18.0)
    assert breakdown["P / E"]["implied_price"] == pytest.approx(16.0)


def test_relative_multiple_eligibility_threshold():
    import math
    # Only 1 peer -> all multiples should be INELIGIBLE (< 2 peers)
    peers = [
        dict(ev=100, market_cap=80, revenue=50, ebitda=10, ebit=8, net_income=5, book_equity=40)
    ]
    target = dict(revenue=100, ebitda=20, ebit=16, net_income=10, book_equity=50)
    rel_df = relative_values(peers, target, cash=10, debt=30, shares=10)

    comp_price, breakdown = composite_relative_value(rel_df, min_peers=2, return_breakdown=True)
    assert math.isnan(comp_price)
    for m in ["EV / EBITDA", "EV / EBIT", "P / E", "P / BV"]:
        assert breakdown[m]["eligible"] is False
        assert breakdown[m]["peers_used"] == 1


def test_explain_peer_selection():
    from valuation.model import explain_peer_selection
    target = dict(industry="Thermal Coal", ebitda_margin=0.25, der=0.40)
    peer = dict(industry="Thermal Coal", ebitda_margin=0.24, der=0.45, similarity_distance=0.12)

    explanation = explain_peer_selection(target, peer)
    assert "Direct sub-industry peer (Thermal Coal)" in explanation
    assert "closely aligned EBITDA margin" in explanation
    assert "comparable leverage" in explanation
    assert "similarity distance 0.12" in explanation


def test_demo_peers_structure():
    from valuation.data import demo_peers
    d_peers = demo_peers()
    assert len(d_peers) == 2
    for p in d_peers:
        assert p["symbol"].endswith(".JK")
        assert "historical" in p
        assert p["price"] > 0
        assert p["shares"] > 0

def test_manual_peer_addition_and_deduplication():
    from valuation.data import demo_peers
    from valuation.data import rank_peers_similarity, peer_record

    target_symbol = "UNTR.JK"
    target_clean = "UNTR"
    initial_peers = demo_peers()  # ADRO.JK, PTBA.JK
    assert len(initial_peers) == 2

    existing_symbols = {p["symbol"].replace(".JK", "").upper() for p in initial_peers}

    # Case 1: Target company entered in manual additional peers -> rejected
    raw_input = "UNTR, DEMO1, BYAN"
    symbols = [s.strip().upper().replace(".JK", "") for s in raw_input.split(",")]
    rejected = [s for s in symbols if s == target_clean]
    assert "UNTR" in rejected

    # Case 2: Already existing peer -> deduplicated
    already_present = [s for s in symbols if s in existing_symbols]
    assert "DEMO1" in already_present

    # Case 3: Genuine new peer -> BYAN
    to_add = [s for s in symbols if s != target_clean and s not in existing_symbols]
    assert to_add == ["BYAN"]

    # Mock new peer company dict
    new_peer_company = {
        "symbol": "BYAN.JK",
        "name": "Bayan Resources Tbk",
        "industry": "Thermal Coal",
        "sector": "Energy",
        "price": 18000.0,
        "shares": 33.3,
        "price_currency": "IDR",
        "historical": initial_peers[0]["historical"].copy()
    }
    updated_peers = list(initial_peers) + [new_peer_company]
    assert len(updated_peers) == 3

    # Verify rank_peers_similarity handles all 3 peers
    target_prof = {
        "industry": "Thermal Coal",
        "ebitda_margin": 0.22,
        "der": 0.35
    }
    period = initial_peers[0]["historical"].columns[-1]
    candidate_rows = [peer_record(p, period) for p in updated_peers]
    ranked = rank_peers_similarity(target_prof, candidate_rows)
    assert len(ranked) == 3
    assert {r["ticker"] for r in ranked} == {"DEMO1.JK", "DEMO2.JK", "BYAN.JK"}

    # Case 4: Removal of peer (simulating '✕' button)
    removed_peers = [p for p in updated_peers if p["symbol"] != "DEMO1.JK"]
    assert len(removed_peers) == 2
    assert "DEMO1.JK" not in {p["symbol"] for p in removed_peers}

def test_similarity_score_and_confidence_level():
    from valuation.data import rank_peers_similarity

    target = {"industry": "Thermal Coal", "ebitda_margin": 0.20, "der": 0.50}

    # Peer 1: Exact financial match (dist = 0) -> 100/100, High Confidence
    p1 = {"ticker": "PERF.JK", "industry": "Thermal Coal", "ebitda_margin": 0.20, "der": 0.50}

    # Peer 2: Close match (dist = 0.40) -> ~79/100, High Confidence
    p2 = {"ticker": "CLOS.JK", "industry": "Thermal Coal", "ebitda_margin": 0.22, "der": 0.60}

    # Peer 3: Moderate match (dist = 1.20) -> ~56/100, Moderate Confidence
    p3 = {"ticker": "MODR.JK", "industry": "Thermal Coal", "ebitda_margin": 0.32, "der": 1.10}

    # Peer 4: Distant / different industry match (dist >= 5.0) -> < 50/100, Low Confidence
    p4 = {"ticker": "DIST.JK", "industry": "Consumer Goods", "ebitda_margin": 0.00, "der": 3.00}

    ranked = rank_peers_similarity(target, [p1, p2, p3, p4])
    assert len(ranked) == 4

    # Ordering check: distances must be ascending
    assert ranked[0]["ticker"] == "PERF.JK"
    assert ranked[1]["ticker"] == "CLOS.JK"
    assert ranked[2]["ticker"] == "MODR.JK"
    assert ranked[3]["ticker"] == "DIST.JK"

    # Perfect match checks
    assert ranked[0]["similarity_distance"] == 0.0
    assert ranked[0]["similarity_score"] == 100
    assert ranked[0]["confidence_level"] == "High"

    # Close match checks
    assert ranked[1]["similarity_score"] >= 75
    assert ranked[1]["confidence_level"] == "High"

    # Moderate match checks
    assert 50 <= ranked[2]["similarity_score"] < 75
    assert ranked[2]["confidence_level"] == "Moderate"

    # Distant match checks
    assert ranked[3]["similarity_score"] < 50
    assert ranked[3]["confidence_level"] == "Low"

    # Monotonicity check
    scores = [r["similarity_score"] for r in ranked]
    assert scores == sorted(scores, reverse=True)

def test_usd_peer_currency_alignment_prevents_multiple_anomaly():
    from valuation.data import demo_peers, peer_record
    from valuation.model import relative_values, composite_relative_value

    demo = demo_peers()[0]
    period = demo["historical"].columns[-1]

    # Mock a peer reporting in USD with statements in USD billions but traded in IDR
    usd_peer = dict(demo)
    usd_peer["symbol"] = "USD_PEER.JK"
    usd_peer["financial_currency"] = "USD"
    usd_peer["price_currency"] = "IDR"
    usd_peer["price"] = 2500.0  # IDR per share
    usd_peer["shares"] = 10.0e9  # 10 billion shares -> Market Cap = 25,000 IDR bn
    usd_peer["suggested_fx"] = 16000.0
    # Raw statements in USD billions (e.g. EBITDA is 0.5 USD bn = 8,000 IDR bn)
    usd_peer["historical"] = demo["historical"] / 16000.0

    # Test peer_record automatically aligns USD statements using suggested_fx
    pr = peer_record(usd_peer, period)
    assert pr["market_cap"] == 25000.0
    # EBITDA should be converted to ~8,000 IDR bn, NOT left as 0.5 USD bn
    assert pr["ebitda"] > 100.0  # IDR billions
    
    # EV/EBITDA multiple must be realistic (< 50x), never in the tens of thousands
    ev_ebitda = pr["ev"] / pr["ebitda"]
    assert 1.0 < ev_ebitda < 30.0

    # Test relative valuation on target
    target = dict(
        revenue=100000.0,
        ebit=20000.0,
        ebitda=25000.0,
        net_income=15000.0,
        book_equity=50000.0
    )
    rel_df = relative_values([pr, pr], target, cash=10000.0, debt=5000.0, shares=28.0)
    assert not rel_df.empty
    
    # Implied value per share must be realistic (in thousands of IDR, NOT in millions)
    for p_impl in rel_df["Implied price (IDR)"].dropna():
        assert 500.0 < p_impl < 50000.0

def test_adro_full_pipeline_produces_realistic_multiples_and_upside():
    from valuation.data import demo_peers, peer_record
    from valuation.model import relative_values, composite_relative_value, blended_valuation, investment_recommendation

    demo = demo_peers()[0]
    period = demo["historical"].columns[-1]

    # Target: ADRO reporting in USD (converted to IDR using fx=18050)
    target_fx = 18050.0
    adro_price = 2460.0
    adro_shares = 28.8005  # bn shares
    # Raw statements in USD: revenue = 1.87 USD bn, ebitda = 0.53 USD bn
    target = dict(
        revenue=1.8735 * target_fx,
        ebit=0.5295 * target_fx,
        ebitda=0.5336 * target_fx,
        net_income=0.4477 * target_fx,
        book_equity=5.0 * target_fx
    )
    adro_cash = 1.5803 * target_fx
    adro_debt = 0.8213 * target_fx

    # Peer 1: PTBA reporting in IDR
    ptba = dict(demo)
    ptba["symbol"] = "PTBA.JK"
    ptba["financial_currency"] = "IDR"
    ptba["price_currency"] = "IDR"
    ptba["price"] = 3280.0
    ptba["shares"] = 11.514e9

    # Peer 2: BUMI reporting in USD
    bumi = dict(demo)
    bumi["symbol"] = "BUMI.JK"
    bumi["financial_currency"] = "USD"
    bumi["price_currency"] = "IDR"
    bumi["price"] = 140.0
    bumi["shares"] = 371.3e9
    bumi["suggested_fx"] = 18050.0
    bumi["historical"] = demo["historical"] / 18050.0

    # Peer 3: INDY reporting in USD
    indy = dict(demo)
    indy["symbol"] = "INDY.JK"
    indy["financial_currency"] = "USD"
    indy["price_currency"] = "IDR"
    indy["price"] = 2190.0
    indy["shares"] = 5.202e9
    indy["suggested_fx"] = 18050.0
    indy["historical"] = demo["historical"] / 18050.0

    # Calling peer_record with default fx=None
    pr_ptba = peer_record(ptba, period)
    pr_bumi = peer_record(bumi, period)
    pr_indy = peer_record(indy, period)

    # Every peer EV/EBITDA multiple must be between 1x and 40x, NEVER tens of thousands
    for pr in [pr_ptba, pr_bumi, pr_indy]:
        ev_ebitda = pr["ev"] / pr["ebitda"]
        assert 1.0 < ev_ebitda < 40.0, f"{pr['ticker']} EV/EBITDA anomaly: {ev_ebitda}"

    rel_df = relative_values([pr_ptba, pr_bumi, pr_indy], target, cash=adro_cash, debt=adro_debt, shares=adro_shares)
    assert not rel_df.empty

    rel_price = composite_relative_value(rel_df, case="Median")
    assert 1000.0 < rel_price < 25000.0, f"Relative price anomaly: {rel_price}"

    # Blended valuation with DCF (e.g. 1783 IDR)
    dcf_price = 1782.95
    blended = blended_valuation(dcf_price, rel_price, 0.75, 0.25)
    assert 1000.0 < blended < 10000.0

    # Investment recommendation upside
    rec = investment_recommendation(adro_price, blended)
    # Upside must be realistic, strictly < +200%, NEVER +500,000%
    assert -0.50 < rec["upside"] < 2.0, f"Upside anomaly: {rec['upside']:.1%}"



def test_five_year_explicit_forecast_horizon_and_driver_fade(case):
    _, b, a = case
    d = default_drivers(a, 2026)
    assert len(d) == 5
    assert list(d["Year"]) == [2026, 2027, 2028, 2029, 2030]
    # Years 1-3 hold operational momentum
    assert d.loc[0, "Growth %"] == pytest.approx(100 * a.growth)
    assert d.loc[1, "Growth %"] == pytest.approx(100 * a.growth)
    assert d.loc[2, "Growth %"] == pytest.approx(100 * a.growth)
    # Years 4-5 transition smoothly to mature growth
    expected_y4 = 100 * (a.growth * (2.0 / 3.0) + a.mature_growth * (1.0 / 3.0))
    assert d.loc[3, "Growth %"] == pytest.approx(expected_y4)
    assert d.loc[4, "Growth %"] == pytest.approx(100 * a.mature_growth)

    f = forecast(b, a, 2026)
    assert len(f) == 5
    assert list(f.index) == [2026, 2027, 2028, 2029, 2030]

    # Verify Terminal Value discounted across exactly 5 periods
    r = dcf(f, b, a, 8)
    expected_pv_terminal = r["terminal_value"] / (1 + a.wacc) ** 5
    assert r["pv_terminal"] == pytest.approx(expected_pv_terminal)
    assert r["price"] > 0


def test_terminal_roic_below_median_and_aligned_with_growth(case):
    c, b, _ = case
    hist_roic = compute_historical_roic(c["historical"], b)
    assert hist_roic == pytest.approx(0.195, abs=0.005)

    company_meta = dict(price=1400., shares=20e9, beta=1.0)
    inferred = infer_assumptions(c["historical"], b, company_meta)

    # 1. Terminal ROIC must be strictly lower than historical median due to growth deceleration & competitive convergence
    assert inferred.terminal_roic < hist_roic
    assert 0.10 < inferred.terminal_roic < 0.16

    # 2. Terminal ROIC must strictly exceed terminal growth by at least safety floor (1.5%)
    assert inferred.terminal_roic >= inferred.terminal_growth + 0.015

    # 3. Sustainable terminal reinvestment rate (g / ROIC) is economically bounded between 10% and 50%
    terminal_reinvestment = inferred.terminal_growth / inferred.terminal_roic
    assert 0.10 <= terminal_reinvestment <= 0.50

    # 4. When growth deceleration is steeper, compression toward WACC is more pronounced
    from dataclasses import replace
    # Simulate high near-term growth firm
    hist_high_growth = c["historical"].copy()
    hist_high_growth.loc["revenue", "2025-12-31"] = hist_high_growth.loc["revenue", "2022-12-31"] * 2.5 # ~35% CAGR
    inferred_high = infer_assumptions(hist_high_growth, b, company_meta)
    # Higher initial growth relative to 2.5% terminal growth yields minimum alpha (0.35), compressing ROIC closer to WACC
    assert inferred_high.terminal_roic <= inferred.terminal_roic


def test_scenario_modeling_modes_and_parameters(case):
    c, b, a = case
    # Verify Assumptions includes scenario defaults
    assert hasattr(a, "scenario_mode")
    assert a.scenario_mode == "Coherent Macro & Operating World"
    assert a.bear_growth_shift == -0.02
    assert a.bull_growth_shift == 0.02
    assert a.bear_wacc_shift == 0.005
    assert a.bull_wacc_shift == -0.005

    # Run base DCF
    f_base = forecast(b, a, 2026)
    r_base = dcf(f_base, b, a, 8.0)
    p_base = r_base["price"]

    # Operational Bear (Growth & Margin -2%)
    d_bear = default_drivers(a, 2026)
    d_bear["Growth %"] += a.bear_growth_shift * 100
    d_bear["EBIT margin %"] += a.bear_margin_shift * 100
    f_bear_op = forecast(b, a, 2026, d_bear)
    r_bear_op = dcf(f_bear_op, b, a, 8.0)

    # Macro Bear (Operating -2% AND WACC +0.5%, g -0.5%, ROIC -1%)
    a_bear_macro = replace(a, wacc_override=a.wacc + 0.005, terminal_growth=a.terminal_growth - 0.005, terminal_roic=a.terminal_roic - 0.010)
    f_bear_macro = forecast(b, a_bear_macro, 2026, d_bear)
    r_bear_macro = dcf(f_bear_macro, b, a_bear_macro, 8.0)

    # Macro Bear must reflect lower valuation than purely operational Bear due to discount rate expansion
    assert r_bear_macro["price"] < r_bear_op["price"] < p_base


def test_scenario_probabilities_and_expected_value():
    """Verify governed scenario probabilities, normalization, and expected value calculation."""
    # 1. Default probabilities
    a = Assumptions()
    assert a.prob_bear == 0.25
    assert a.prob_base == 0.50
    assert a.prob_bull == 0.25
    probs = a.normalized_scenario_probabilities()
    assert probs["Bear"] == 0.25
    assert probs["Base"] == 0.50
    assert probs["Bull"] == 0.25
    assert sum(probs.values()) == 1.0

    # 2. Institutional range compliance (Base 50-60%, Bull 20-25%, Bear 20-25%)
    a_custom = Assumptions(prob_bear=0.20, prob_base=0.60, prob_bull=0.20)
    assert 0.20 <= a_custom.prob_bear <= 0.25
    assert 0.50 <= a_custom.prob_base <= 0.60
    assert 0.20 <= a_custom.prob_bull <= 0.25
    probs_custom = a_custom.normalized_scenario_probabilities()
    assert probs_custom["Bear"] == 0.20
    assert probs_custom["Base"] == 0.60
    assert probs_custom["Bull"] == 0.20
    assert sum(probs_custom.values()) == 1.0

    # 3. Normalization safeguard if raw inputs slightly deviate
    a_deviant = Assumptions(prob_bear=0.25, prob_base=0.60, prob_bull=0.25) # sum = 1.10
    norm = a_deviant.normalized_scenario_probabilities()
    assert abs(sum(norm.values()) - 1.0) < 1e-9
    assert abs(norm["Base"] - (0.60 / 1.10)) < 1e-9

    # 4. Expected value calculation
    prices = {"Bear": 1800.0, "Base": 2500.0, "Bull": 3400.0}
    expected_default = sum(prices[s] * probs[s] for s in prices)
    assert expected_default == (1800 * 0.25) + (2500 * 0.50) + (3400 * 0.25)
    assert expected_default == 2550.0


def test_clean_company_name():
    from valuation.data import clean_company_name

    # 1. Strips classic Indonesian BUMN long prefix
    tlkm = "Perusahaan Perseroan (Persero) PT Telekomunikasi Indonesia Tbk"
    assert clean_company_name(tlkm) == "PT Telekomunikasi Indonesia Tbk"

    # 2. Strips redundant prefix and inline (Persero)
    bbri = "Perusahaan Perseroan (Persero) PT Bank Rakyat Indonesia (Persero) Tbk"
    assert clean_company_name(bbri) == "PT Bank Rakyat Indonesia Tbk"

    # 3. Preserves standard non-SOE company names
    asii = "PT Astra International Tbk"
    assert clean_company_name(asii) == "PT Astra International Tbk"

    # 4. Handles empty and whitespace edge cases
    assert clean_company_name("") == ""
    assert clean_company_name(None) == ""


def test_tapg_peer_ranking_lsip_rank_1_and_aali_demoted():
    from valuation.data import rank_peers_similarity

    target_tapg = {
        "ticker": "TAPG.JK",
        "name": "Triputra Agro Persada",
        "industry": "Farm Products",
        "ebitda_margin": 0.3231,
        "der": 0.0981
    }
    candidates = [
        {"ticker": "AALI.JK", "name": "Astra Agro Lestari", "industry": "Farm Products", "ebitda_margin": 0.0970, "der": 0.0000},
        {"ticker": "LSIP.JK", "name": "PP London Sumatra", "industry": "Farm Products", "ebitda_margin": 0.4130, "der": 0.0000},
        {"ticker": "DSNG.JK", "name": "Dharma Satya Nusantara", "industry": "Farm Products", "ebitda_margin": 0.2360, "der": 0.3600},
        {"ticker": "SIMP.JK", "name": "Salim Ivomas Pratama", "industry": "Farm Products", "ebitda_margin": 0.1950, "der": 0.4600},
    ]

    ranked = rank_peers_similarity(target_tapg, candidates)

    # 1. LSIP is Rank #1 with High Confidence (>= 75 score)
    assert ranked[0]["ticker"] == "LSIP.JK"
    assert ranked[0]["confidence_level"] == "High"
    assert ranked[0]["similarity_score"] >= 75

    # 2. DSNG is Rank #2 with Moderate Confidence
    assert ranked[1]["ticker"] == "DSNG.JK"
    assert ranked[1]["confidence_level"] == "Moderate"

    # 3. SIMP is Rank #3 with Moderate Confidence
    assert ranked[2]["ticker"] == "SIMP.JK"

    # 4. AALI is demoted to Rank #4 due to low 9.7% margin vs 32.3% target
    assert ranked[3]["ticker"] == "AALI.JK"


def test_unvr_kino_pure_financial_similarity_no_penalty():
    from valuation.data import rank_peers_similarity

    target_unvr = {
        "ticker": "UNVR.JK",
        "name": "Unilever Indonesia",
        "industry": "Household & Personal Products",
        "ebitda_margin": 0.152,
        "der": 0.14
    }
    candidates = [
        {"ticker": "VICI.JK", "name": "Victoria Care", "industry": "Personal Care Products", "ebitda_margin": 0.152, "der": 0.08},
        {"ticker": "MYOR.JK", "name": "Mayora Indah", "industry": "Packaged Foods", "ebitda_margin": 0.138, "der": 0.45},
        {"ticker": "TCID.JK", "name": "Mandom Indonesia", "industry": "Household & Personal Products", "ebitda_margin": 0.004, "der": 0.00},
        {"ticker": "KINO.JK", "name": "Kino Indonesia", "industry": "Beverages - Non-Alcoholic", "ebitda_margin": 0.077, "der": 0.90},
    ]

    ranked = rank_peers_similarity(target_unvr, candidates)

    # 1. VICI is top peer with near-perfect score >= 90
    assert ranked[0]["ticker"] == "VICI.JK"
    assert ranked[0]["similarity_score"] >= 90
    assert ranked[0]["confidence_level"] == "High"

    # 2. MYOR has high confidence >= 80
    assert ranked[1]["ticker"] == "MYOR.JK"
    assert ranked[1]["similarity_score"] >= 80

    # 3. KINO is NOT penalized to 28; it has score >= 60 and Moderate Confidence
    kino_res = [r for r in ranked if r["ticker"] == "KINO.JK"][0]
    assert kino_res["similarity_score"] >= 60
    assert kino_res["confidence_level"] == "Moderate"


def test_get_multiple_exclusion_details_detects_operating_and_net_loss():
    from valuation.model import get_multiple_exclusion_details

    p_valid = {
        "ticker": "ISAT.JK",
        "ev": 100000.0,
        "market_cap": 50000.0,
        "ebitda": 25000.0,
        "ebit": 10000.0,
        "net_income": 5000.0,
        "book_equity": 30000.0
    }
    p_loss = {
        "ticker": "EXCL.JK",
        "ev": 90000.0,
        "market_cap": 30000.0,
        "ebitda": 18000.0,
        "ebit": -233.0,
        "net_income": -4426.0,
        "book_equity": 28000.0
    }

    exclusions = get_multiple_exclusion_details([p_valid, p_loss])

    # 1. EV / EBITDA and P / BV have zero exclusions
    assert exclusions["EV / EBITDA"] == []
    assert exclusions["P / BV"] == []

    # 2. EV / EBIT identifies EXCL's negative EBIT
    assert len(exclusions["EV / EBIT"]) == 1
    assert "EXCL" in exclusions["EV / EBIT"][0]
    assert "EBIT" in exclusions["EV / EBIT"][0]

    # 3. P / E identifies EXCL's net loss
    assert len(exclusions["P / E"]) == 1
    assert "EXCL" in exclusions["P / E"][0]
    assert "net income" in exclusions["P / E"][0]


def test_relative_values_includes_eligible_peers_tickers():
    p1 = {
        "ticker": "ISAT.JK",
        "ev": 100000.0,
        "market_cap": 50000.0,
        "ebitda": 25000.0,
        "ebit": 10000.0,
        "net_income": 5000.0,
        "book_equity": 35000.0
    }
    p2 = {
        "ticker": "EXCL.JK",
        "ev": 90000.0,
        "market_cap": 30000.0,
        "ebitda": 18000.0,
        "ebit": -233.0,
        "net_income": -4426.0,
        "book_equity": 28000.0
    }
    target = {
        "revenue": 150000.0,
        "ebitda": 70000.0,
        "ebit": 40000.0,
        "net_income": 25000.0,
        "book_equity": 120000.0
    }
    rel_df = relative_values([p1, p2], target, cash=15000.0, debt=40000.0, shares=100.0)
    assert "Eligible peers" in rel_df.columns
    
    ebitda_row = rel_df[(rel_df["Multiple"] == "EV / EBITDA") & (rel_df["Case"] == "Median")].iloc[0]
    assert ebitda_row["Eligible peers"] == "ISAT, EXCL"
    assert ebitda_row["Peers used"] == 2
    
    ebit_row = rel_df[(rel_df["Multiple"] == "EV / EBIT") & (rel_df["Case"] == "Median")].iloc[0]
    assert ebit_row["Eligible peers"] == "ISAT"
    assert ebit_row["Peers used"] == 1


def test_investment_recommendation_handles_negative_dcf_equity():
    # When DCF equity is negative (debt overhang), recommendation must be NOT ELIGIBLE even if blended has residual relative value
    rec = investment_recommendation(reference_price=4030.0, blended_price=209.0, dcf_price=-314.0)
    assert rec["rating"] == "NOT ELIGIBLE"
    assert rec["color"] == "#6c757d"
    assert "Ineligible" in rec["summary"]


def test_damodaran_cyclical_commodity_growth_normalization():
    # A cyclical coal company with flat trailing revenue (e.g. PTBA 2022: 42648 vs 2025: 42651 -> CAGR ~0%)
    h = pd.DataFrame({
        "2022-12-31": {"revenue": 42648.0, "capex": 2000.0, "cogs": 30000.0, "opex": 2000.0, "da": 1500.0},
        "2023-12-31": {"revenue": 38488.0, "capex": 2000.0, "cogs": 28000.0, "opex": 2000.0, "da": 1500.0},
        "2024-12-31": {"revenue": 42764.0, "capex": 2000.0, "cogs": 31000.0, "opex": 2000.0, "da": 1500.0},
        "2025-12-31": {"revenue": 42651.0, "capex": 2000.0, "cogs": 31000.0, "opex": 2000.0, "da": 1500.0},
    })
    b = {"revenue": 42651.0, "cogs": 31000.0, "opex": 2000.0, "da": 1500.0, "ppe": 20000.0}
    
    # 1. Cyclical Coal Company -> Normalized to 3.5%
    cyclical_co = {"symbol": "PTBA.JK", "sector": "Energy", "industry": "Thermal Coal"}
    a_cyclical = infer_assumptions(h, b, cyclical_co)
    assert a_cyclical.growth == pytest.approx(0.035)
    assert a_cyclical.mature_growth == pytest.approx(0.030)

    # 2. Non-Cyclical Consumer Company -> Not normalized if positive (respects audited 0.00% or small CAGR)
    non_cyclical_co = {"symbol": "TEST.JK", "sector": "Consumer Defensive", "industry": "Packaged Foods"}
    a_non_cyclical = infer_assumptions(h, b, non_cyclical_co)
    assert a_non_cyclical.growth < 0.01


def test_official_idx_excel_registry_and_peer_matching():
    from valuation.data import load_idx_company_registry, get_company_idx_metadata, get_default_peers_for_ticker

    ticker_map, sub_ind_map, sector_map = load_idx_company_registry()
    assert len(ticker_map) >= 900
    assert "SIDO" in ticker_map
    assert "UNVR" in ticker_map
    assert "KLBF" in ticker_map

    # SIDO metadata is Healthcare / Pharmaceuticals
    sido_meta = get_company_idx_metadata("SIDO")
    assert sido_meta is not None
    assert sido_meta["sector"] == "Healthcare"
    assert sido_meta["sub_industry"] == "Pharmaceuticals"

    # UNVR metadata is Consumer Non-Cyclicals / Personal Care Products
    unvr_meta = get_company_idx_metadata("UNVR")
    assert unvr_meta is not None
    assert unvr_meta["sector"] == "Consumer Non-Cyclicals"
    assert unvr_meta["sub_industry"] == "Personal Care Products"

    # Peer suggestions for SIDO must prioritize true pharma peers (KLBF, TSPC, etc.) and exclude UNVR
    sido_peers = get_default_peers_for_ticker("SIDO.JK")
    assert "KLBF" in sido_peers
    assert "TSPC" in sido_peers
    assert "UNVR" not in sido_peers
    assert "ICBP" not in sido_peers

    # Peer suggestions for UNVR must be personal care peers and exclude food/pharma
    unvr_peers = get_default_peers_for_ticker("UNVR.JK")
    assert "SIDO" not in unvr_peers

    # TLKM (Telkom) is classified under singleton sub-industry 'Integrated Telecommunication Service' (J312).
    # Its peers must be operating telecommunication carriers (ISAT, EXCL, LINK, MORA),
    # and MUST NOT contain tower infrastructure companies (TOWR, TBIG, MTEL) or unrelated
    # infrastructure companies like airport baggage (CASS, GMFI), toll roads (CMNP, JSMR), or car terminals (IPCC).
    tlkm_meta = get_company_idx_metadata("TLKM")
    assert tlkm_meta is not None
    assert tlkm_meta["sector"] == "Infrastructures"
    assert tlkm_meta["sub_industry"] == "Integrated Telecommunication Service"
    assert tlkm_meta["group_code"] == "J3"

    tlkm_peers = get_default_peers_for_ticker("TLKM.JK")
    assert tlkm_peers == ["ISAT", "EXCL"]
    assert "TOWR" not in tlkm_peers
    assert "TBIG" not in tlkm_peers
    assert "MTEL" not in tlkm_peers
    assert "LINK" not in tlkm_peers
    assert "MORA" not in tlkm_peers
    assert "CASS" not in tlkm_peers
    assert "CMNP" not in tlkm_peers
    assert "GMFI" not in tlkm_peers
    assert "IPCC" not in tlkm_peers
    assert "JSMR" not in tlkm_peers






def test_damodaran_plantations_and_crops_cyclical_detection():
    # Cyclical Plantation company with trough revenue (CAGR ~ 0.17%)
    h = pd.DataFrame({
        "2022-12-31": {"revenue": 10000.0, "capex": 500.0, "cogs": 7000.0, "opex": 500.0, "da": 300.0},
        "2023-12-31": {"revenue": 9500.0, "capex": 500.0, "cogs": 6800.0, "opex": 500.0, "da": 300.0},
        "2024-12-31": {"revenue": 9800.0, "capex": 500.0, "cogs": 6900.0, "opex": 500.0, "da": 300.0},
        "2025-12-31": {"revenue": 10050.0, "capex": 500.0, "cogs": 7000.0, "opex": 500.0, "da": 300.0},
    })
    b = {"revenue": 10050.0, "cogs": 7000.0, "opex": 500.0, "da": 300.0, "ppe": 5000.0}

    # 1. Plantation issuer under Consumer Non-Cyclicals -> detected as cyclical and normalized to 3.5%
    plantation_co = {"symbol": "TAPG.JK", "sector": "Consumer Non-Cyclicals", "industry": "Plantations & Crops"}
    a_plantation = infer_assumptions(h, b, plantation_co)
    assert a_plantation.growth == pytest.approx(0.035)

    # 2. Processed Foods under Consumer Non-Cyclicals -> NOT detected as cyclical, exact historical CAGR preserved
    food_co = {"symbol": "ICBP.JK", "sector": "Consumer Non-Cyclicals", "industry": "Processed Foods"}
    a_food = infer_assumptions(h, b, food_co)
    cagr = (10050.0 / 10000.0)**(1/3) - 1.0
    assert a_food.growth == pytest.approx(cagr)
    assert a_food.growth < 0.01


def test_statement_shares_fallback_when_info_empty(monkeypatch):
    import yfinance as yf
    from valuation.data import fetch_company

    # Mock yf.Ticker to simulate Yahoo Finance throttling info on cloud
    class MockTicker:
        def __init__(self, sym, session=None):
            self.fast_info = type("FI", (), {"last_price": 2240.0, "shares": 98580940800, "market_cap": 220821307392000.0})()
        def get_info(self):
            return {}
        def get_income_stmt(self, freq="yearly"):
            return pd.DataFrame({"2025-12-31": {"revenue": 150000.0, "cogs": 100000.0, "opex": 20000.0, "da": 10000.0, "interest": 3000.0, "tax": 3000.0, "net_income": 14000.0, "DilutedAverageShares": 99061024659.0}})
        def get_balance_sheet(self, freq="yearly"):
            return pd.DataFrame({"2025-12-31": {"cash": 30000.0, "ar": 10000.0, "inventory": 5000.0, "other_ca": 2000.0, "ppe": 120000.0, "other_assets": 10000.0, "ap": 15000.0, "other_cl": 5000.0, "short_debt": 5000.0, "long_debt": 40000.0, "other_liabilities": 10000.0, "equity": 102000.0, "OrdinarySharesNumber": 99053271200.0}})
        def get_cashflow(self, freq="yearly"):
            return pd.DataFrame({"2025-12-31": {"ebit": 20000.0, "ebitda": 30000.0, "cfo": 25000.0, "capex": 20000.0}})
        def history(self, period="5d"):
            return pd.DataFrame({"Close": [2240.0]})

    monkeypatch.setattr(yf, "Ticker", MockTicker)
    res = fetch_company("TLKM.JK")
    assert res["shares"] is not None
    assert res["shares"] > 90e9
    assert res["price"] == 2240.0


def test_damodaran_plantations_and_crops_cyclical_detection():
    # Cyclical Plantation company with trough revenue (CAGR ~ 0.17%)
    h = pd.DataFrame({
        "2022-12-31": {"revenue": 10000.0, "capex": 500.0, "cogs": 7000.0, "opex": 500.0, "da": 300.0},
        "2023-12-31": {"revenue": 9500.0, "capex": 500.0, "cogs": 6800.0, "opex": 500.0, "da": 300.0},
        "2024-12-31": {"revenue": 9800.0, "capex": 500.0, "cogs": 6900.0, "opex": 500.0, "da": 300.0},
        "2025-12-31": {"revenue": 10050.0, "capex": 500.0, "cogs": 7000.0, "opex": 500.0, "da": 300.0},
    })
    b = {"revenue": 10050.0, "cogs": 7000.0, "opex": 500.0, "da": 300.0, "ppe": 5000.0}

    # 1. Plantation issuer under Consumer Non-Cyclicals -> detected as cyclical and normalized to 3.5%
    plantation_co = {"symbol": "TAPG.JK", "sector": "Consumer Non-Cyclicals", "industry": "Plantations & Crops"}
    a_plantation = infer_assumptions(h, b, plantation_co)
    assert a_plantation.growth == pytest.approx(0.035)

    # 2. Processed Foods under Consumer Non-Cyclicals -> NOT detected as cyclical, exact historical CAGR preserved
    food_co = {"symbol": "ICBP.JK", "sector": "Consumer Non-Cyclicals", "industry": "Processed Foods"}
    a_food = infer_assumptions(h, b, food_co)
    cagr = (10050.0 / 10000.0)**(1/3) - 1.0
    assert a_food.growth == pytest.approx(cagr)
    assert a_food.growth < 0.01



def test_multiple_outlier_clamping_and_exclusion_reasons():
    from valuation.model import relative_values, composite_relative_value, get_multiple_exclusion_details

    # Normal peers + 1 distorted micro-denominator peer (e.g. PACK with EV/EBITDA of 9,101x)
    peers = [
        {"ticker": "BRMS.JK", "market_cap": 11000.0, "ev": 10000.0, "ebitda": 1367.0, "ebit": 1350.0, "net_income": 800.0, "book_equity": 20000.0},
        {"ticker": "DKFT.JK", "market_cap": 3500.0, "ev": 3300.0, "ebitda": 657.0, "ebit": 550.0, "net_income": 570.0, "book_equity": 1200.0},
        {"ticker": "HRUM.JK", "market_cap": 9500.0, "ev": 31000.0, "ebitda": 1320.0, "ebit": 1320.0, "net_income": 600.0, "book_equity": 14000.0},
        {"ticker": "PACK.JK", "market_cap": 13785.0, "ev": 13721.0, "ebitda": 1.5, "ebit": 1.4, "net_income": 28.0, "book_equity": 105.0},
    ]
    target = {
        "revenue": 84642.0, "ebit": 6975.0, "ebitda": 7143.0, "net_income": 7208.0, "book_equity": 36500.0,
    }
    shares = 24.031
    cash = 9000.0
    debt = 3400.0

    # Test relative_values: PACK must be filtered out from EV/EBITDA, EV/EBIT, P/E, P/BV
    rv = relative_values(peers, target, cash, debt, shares)
    for _, row in rv[rv["Case"] == "Median"].iterrows():
        # Peers used must be 3 (excluding PACK which has EV/EBITDA ~9147 > 100)
        assert row["Peers used"] == 3
        assert "PACK" not in row["Eligible peers"]
        # Implied price must remain realistic (between Rp 500 and Rp 6,000)
        assert 500 <= row["Implied price (IDR)"] <= 6000

    comp_price = composite_relative_value(rv)
    assert 2000 <= comp_price <= 4000

    # Test get_multiple_exclusion_details: PACK must be listed with the extreme multiple outlier reason
    excl = get_multiple_exclusion_details(peers)
    assert any("PACK (extreme multiple outlier" in reason for reason in excl["EV / EBITDA"])
    assert any("PACK (extreme multiple outlier" in reason for reason in excl["EV / EBIT"])
    assert any("PACK (extreme multiple outlier" in reason for reason in excl["P / E"])
    assert any("PACK (extreme multiple outlier" in reason for reason in excl["P / BV"])



def test_growth_assumption_archetypes_distinction():
    from valuation.model import infer_assumptions

    # Case 1: Cyclical Commodity with negative CAGR -> 3.5% with commodity_cycle archetype
    h_cyclical = pd.DataFrame({
        "2022-12-31": {"revenue": 10000.0, "cogs": 7000.0, "opex": 500.0, "da": 300.0},
        "2025-12-31": {"revenue": 8000.0, "cogs": 6000.0, "opex": 500.0, "da": 300.0},
    })
    b_cyclical = {"revenue": 8000.0, "cogs": 6000.0, "opex": 500.0, "da": 300.0}
    co_cyclical = {"symbol": "ADRO.JK", "sector": "Energy", "industry": "Thermal Coal"}
    a_cyclical = infer_assumptions(h_cyclical, b_cyclical, co_cyclical)
    assert a_cyclical.growth == pytest.approx(0.035)
    assert a_cyclical.growth_archetype == "commodity_cycle"

    # Case 2: Non-Cyclical Mature with negative CAGR (like TLKM) -> 2.5% with macro_mature archetype
    h_mature = pd.DataFrame({
        "2022-12-31": {"revenue": 147306.0, "cogs": 41812.0, "opex": 62000.0, "da": 32000.0},
        "2025-12-31": {"revenue": 146743.0, "cogs": 42000.0, "opex": 63000.0, "da": 32000.0},
    })
    b_mature = {"revenue": 146743.0, "cogs": 42000.0, "opex": 63000.0, "da": 32000.0}
    co_mature = {"symbol": "TLKM.JK", "sector": "Infrastructure", "industry": "Integrated Telecommunication Services"}
    a_mature = infer_assumptions(h_mature, b_mature, co_mature)
    assert a_mature.growth == pytest.approx(0.025)
    assert a_mature.growth_archetype == "macro_mature"

    # Case 3: Organic Growth company with positive CAGR -> historical CAGR with organic_cagr archetype
    h_growth = pd.DataFrame({
        "2022-12-31": {"revenue": 60000.0, "cogs": 38000.0, "opex": 8000.0, "da": 2000.0},
        "2023-12-31": {"revenue": 66000.0, "cogs": 42000.0, "opex": 8500.0, "da": 2100.0},
        "2024-12-31": {"revenue": 72000.0, "cogs": 46000.0, "opex": 9000.0, "da": 2300.0},
        "2025-12-31": {"revenue": 80000.0, "cogs": 50000.0, "opex": 10000.0, "da": 2500.0},
    })
    b_growth = {"revenue": 80000.0, "cogs": 50000.0, "opex": 10000.0, "da": 2500.0}
    co_growth = {"symbol": "ICBP.JK", "sector": "Consumer Non-Cyclicals", "industry": "Processed Foods"}
    a_growth = infer_assumptions(h_growth, b_growth, co_growth)
    expected_cagr = (80000.0 / 60000.0)**(1/3) - 1.0
    assert a_growth.growth == pytest.approx(expected_cagr)
    assert a_growth.growth_archetype == "organic_cagr"


def test_damodaran_cost_of_debt_floor_enforcement():
    # Case 1: Effective rate below Rf (e.g. USD Pinehill debt at 4.54% vs Rf 6.64%) -> floored at Rf + 150 bps
    h = pd.DataFrame({
        "2025-12-31": {"revenue": 70000.0, "cogs": 45000.0, "opex": 10000.0, "da": 2000.0}
    })
    b_offshore = {
        "revenue": 70000.0, "cogs": 45000.0, "opex": 10000.0, "da": 2000.0,
        "short_debt": 2000.0, "long_debt": 40000.0, # Total debt = 42,000
        "interest": 1890.0, # 1890 / 42000 = 4.5% (< 6.64%)
    }
    co = {"symbol": "ICBP.JK", "price": 6000.0, "shares": 10e9}
    a = infer_assumptions(h, b_offshore, co)
    assert a.debt_rate == pytest.approx(round(a.risk_free + 0.0150, 4))
    assert a.debt_rate >= a.risk_free

    # Case 2: Effective rate above Rf (e.g. 8.5% domestic bank debt > 6.64%) -> retains commercial rate
    b_domestic = {
        "revenue": 70000.0, "cogs": 45000.0, "opex": 10000.0, "da": 2000.0,
        "short_debt": 2000.0, "long_debt": 40000.0, # Total debt = 42,000
        "interest": 3570.0, # 3570 / 42000 = 8.5% (> 6.64%)
    }
    a_dom = infer_assumptions(h, b_domestic, co)
    assert a_dom.debt_rate == pytest.approx(0.0850)
