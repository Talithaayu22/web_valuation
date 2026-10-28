"""Unit tests for the Institutional Valuation Report PDF Generator."""
import pytest
from valuation.model import Assumptions
from valuation.report_pdf import generate_valuation_pdf, create_scenario_chart


def test_create_scenario_chart():
    chart = create_scenario_chart(
        market_price=1500.0,
        bear_price=1200.0,
        base_price=1550.0,
        bull_price=1900.0,
        central_price=1580.0
    )
    assert chart is not None
    assert chart.width == 530
    assert chart.height == 125


def test_generate_valuation_pdf_basic():
    company = {
        "symbol": "AKRA.JK",
        "name": "PT AKR Corporindo Tbk",
        "sector": "Energy",
        "industry": "Oil, Gas & Chemical Distribution",
        "price": 1480.0,
        "fetched_at": "2026-10-24T12:00:00Z"
    }
    assumptions = Assumptions(prob_bear=0.25, prob_base=0.50, prob_bull=0.25)
    dcf_result = {"price": 1768.0, "equity_value": 35000.0}
    scenario_rows = [
        {"Scenario": "Bear", "Probability": 0.25, "Value / share": 1130.0},
        {"Scenario": "Base", "Probability": 0.50, "Value / share": 1617.0},
        {"Scenario": "Bull", "Probability": 0.25, "Value / share": 2264.0},
    ]
    rel_breakdown = {
        "EV / EBITDA": {"implied_price": 1174.0},
        "P / E": {"implied_price": 1149.0},
        "P / BV": {"implied_price": 957.0},
    }

    pdf_bytes = generate_valuation_pdf(
        company=company,
        assumptions=assumptions,
        dcf_result=dcf_result,
        scenario_rows=scenario_rows,
        rel_breakdown=rel_breakdown,
        rel_price=1162.0,
        blended_price=1657.0,
        effective_price=1657.0,
        expected_dcf_price=1680.0,
        rec={
            "rating": "HOLD / NEUTRAL",
            "color": "#C97D1A",
            "upside": 0.119,
            "margin_of_safety": 0.15,
            "summary": "Implied upside is within the neutral range."
        },
        approach_eval={
            "rationale": "75% DCF anchor / 25% peer cross-check",
            "dcf_weight": 0.75,
            "rel_weight": 0.25,
            "quality": "High"
        },
        peer_rows=[
            {"symbol": "PEER1.JK", "name": "Peer One Tbk", "ebitda_margin": 0.20, "der": 0.5, "ev_ebitda": 6.0, "ev_ebit": 8.5, "pe": 12.0, "pbv": 1.5}
        ]
    )

    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 2000
    assert pdf_bytes.startswith(b"%PDF-")


def test_generate_valuation_pdf_edge_cases():
    # Empty / none values should not throw an exception
    pdf_bytes = generate_valuation_pdf(
        company=None,
        assumptions=None,
        dcf_result=None,
        scenario_rows=None,
        relative_df=None,
        rel_breakdown=None,
        rel_price=None,
        blended_price=None,
        effective_price=None,
        expected_dcf_price=None,
        rec=None,
        approach_eval=None,
        peer_rows=None,
    )
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF-")


def test_generate_valuation_pdf_page_budget_exact_2_pages():
    import re
    from valuation.data import demo_company
    from valuation.model import BASE_FIELDS, forecast, dcf
    c = demo_company()
    b = c["historical"].loc[list(BASE_FIELDS)].iloc[:, -1].to_dict()
    a = Assumptions()
    f = forecast(b, a, 2026)
    r = dcf(f, b, a, 8.0)
    pdf_bytes = generate_valuation_pdf(
        company=c,
        assumptions=a,
        dcf_result=r,
        scenario_rows=[
            {"Scenario": "Bear", "Probability": "25%", "Value / share": 1050.0},
            {"Scenario": "Base", "Probability": "50%", "Value / share": 1380.0},
            {"Scenario": "Bull", "Probability": "25%", "Value / share": 1620.0},
        ],
        effective_price=1380.0,
        rel_price=1350.0,
    )
    page_count = len(re.findall(rb'/Type\s*/Page\b', pdf_bytes))
    assert page_count == 2
    assert len(pdf_bytes) > 20000
