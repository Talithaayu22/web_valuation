from dataclasses import replace
from io import BytesIO
import pandas as pd
import pytest
from openpyxl import load_workbook
from valuation.data import demo_company, normalize, ticker_symbol, peer_record
from valuation.model import (Assumptions, BASE_FIELDS, base_check, forecast, dcf, sensitivity, default_drivers, relative_values, infer_assumptions, composite_relative_value, blended_valuation, evaluate_approach_weights, investment_recommendation)
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
    assert r.loc["EV / Revenue","Implied price (IDR)"] == pytest.approx(18)
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
    assert book["Forecast IDR bn"].max_column == 11


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
        dict(ticker='MEDIUM', industry='Thermal Coal', ebitda_margin=0.15, der=0.80),
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
