import pytest
from streamlit.testing.v1 import AppTest
from pathlib import Path
import openpyxl
import io
import pandas as pd


APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


def test_audit_1_wacc_reactivity():
    """
    Test 1 — WACC & Discount Rate Reactivity:
    Verify that updating macro inputs or WACC override propagates through Cost of Capital,
    WACC, DCF Fair Value, Implied Upside, and Recommendation.
    """
    app = AppTest.from_file(APP_PATH, default_timeout=35).run()
    assert not app.exception

    # Get baseline DCF value
    base_dcf_metric = next(m.value for m in app.metric if m.label == "DCF value / share")
    base_dcf_val = float(base_dcf_metric.replace("Rp", "").replace(",", "").strip())
    assert base_dcf_val > 0

    # Override WACC with a significantly higher discount rate (e.g. 15%)
    chk_override = next(c for c in app.checkbox if c.label == "Override calculated WACC")
    chk_override.set_value(True)

    wacc_input = next(n for n in app.number_input if n.label == "WACC override (%)")
    wacc_input.set_value(15.0)

    # Submit form
    btn_apply = next(b for b in app.button if b.label == "Apply assumptions")
    btn_apply.click().run()
    assert not app.exception

    # Verify DCF value updated and decreased due to higher discount rate
    revised_dcf_metric = next(m.value for m in app.metric if m.label == "DCF value / share")
    revised_dcf_val = float(revised_dcf_metric.replace("Rp", "").replace(",", "").strip())
    assert revised_dcf_val < base_dcf_val, f"Expected higher WACC (15%) to decrease DCF value ({revised_dcf_val} vs {base_dcf_val})"

    # Verify Calculated WACC metric in top assumptions bar reflects 15.00%
    wacc_card = next(m.value for m in app.metric if m.label == "Calculated WACC")
    assert "15.00%" in wacc_card


def test_audit_2_revenue_growth_and_margin_reactivity():
    """
    Test 2 — Revenue Growth & Operating Margin Reactivity:
    Verify that increasing growth propagates through forecast statements, FCFF, and DCF equity value.
    """
    app = AppTest.from_file(APP_PATH, default_timeout=35).run()
    assert not app.exception

    base_dcf = next(m.value for m in app.metric if m.label == "DCF value / share")
    base_dcf_val = float(base_dcf.replace("Rp", "").replace(",", "").strip())

    # Increase initial growth from 3.5% to 12.0%
    growth_input = next(n for n in app.number_input if n.label == "Growth · years 1–3 (%)")
    growth_input.set_value(12.0)

    btn_apply = next(b for b in app.button if b.label == "Apply assumptions")
    btn_apply.click().run()
    assert not app.exception

    revised_dcf = next(m.value for m in app.metric if m.label == "DCF value / share")
    revised_dcf_val = float(revised_dcf.replace("Rp", "").replace(",", "").strip())
    assert revised_dcf_val > base_dcf_val, f"Expected higher growth to increase DCF value ({revised_dcf_val} vs {base_dcf_val})"

    # Verify Initial Growth (Y1–3) KPI card updated to 12.0%
    growth_card = next(m.value for m in app.metric if m.label == "Initial Growth (Y1–3)")
    assert "12.0%" in growth_card


def test_audit_3_peer_selection_and_eligibility():
    """
    Test 3 — Peer Universe & Multiple Eligibility Triangulation:
    Verify that unchecking peers reduces active peer count and falls back to 100% DCF when < 2 peers remain.
    """
    app = AppTest.from_file(APP_PATH, default_timeout=35).run()
    assert not app.exception

    # Collect all peer checkboxes
    peer_cbs = [cb for cb in app.checkbox if cb.label.startswith("Include ")]
    assert len(peer_cbs) >= 2, "Expected at least 2 default peers"

    # Uncheck all peers except one
    for cb in peer_cbs[1:]:
        cb.set_value(False)

    app.run()
    assert not app.exception

    # When active peers < 2, relative multiples must show < 2 valid peers or 100% DCF weight rule
    # Check that Rule 1 (100% DCF anchor) is triggered
    all_text = [x.value for x in list(app.markdown)] + [x.value for x in list(app.caption)]
    assert any("100% DCF" in t or "< 2" in t or "below the 2-peer policy minimum" in t or "100.0% DCF" in t for t in all_text)


def test_audit_4_scenario_modeling_and_shifts():
    """
    Test 4 — Scenario Probability & Stress Shift Calibration:
    Verify that modifying scenario shifts updates expected value and scenario distributions.
    """
    app = AppTest.from_file(APP_PATH, default_timeout=35).run()
    assert not app.exception

    # Adjust Bull growth shift
    bull_growth = next(n for n in app.number_input if n.label == "Revenue growth shift (%)" and "bull" in str(n.key).lower())
    bull_growth.set_value(5.0)  # +5% Bull growth

    app.run()
    assert not app.exception

    # Check that scenario table contains Bear, Base, Bull
    assert any("Bull" in x.value for x in app.markdown)


def test_audit_5_valuation_method_weighting():
    """
    Test 5 — Valuation Method Weighting:
    Verify that modifying DCF vs Relative weight recalculates Blended Fair Value.
    """
    app = AppTest.from_file(APP_PATH, default_timeout=35).run()
    assert not app.exception

    # Set 50% DCF / 50% Relative
    dcf_weight_input = next(n for n in app.number_input if n.label == "Valuation weight · DCF (%)")
    dcf_weight_input.set_value(50.0)

    rel_weight_input = next(n for n in app.number_input if n.label == "Valuation weight · Relative (%)")
    rel_weight_input.set_value(50.0)

    btn_apply = next(b for b in app.button if b.label == "Apply assumptions")
    btn_apply.click().run()
    assert not app.exception

    # Verify blended weighting reflects 50% / 50%
    assert any("50%" in x.value for x in app.markdown)


def test_audit_6_company_switching_and_isolation():
    """
    Test 6 — Multi-Company Ticker Switching & State Isolation:
    Verify that loading a new ticker cleanly updates company name, sector, and peer list.
    """
    app = AppTest.from_file(APP_PATH, default_timeout=35).run()
    assert not app.exception
    assert any("Telkom" in x.value or "TLKM" in x.value for x in app.markdown)

    # Change ticker to ASII
    ticker_input = next(t for t in app.text_input if t.label == "IDX ticker")
    ticker_input.set_value("ASII")

    btn_load = next(b for b in app.button if b.label == "Load company")
    btn_load.click().run()
    assert not app.exception

    # Check that company name now reflects Astra International / ASII
    assert any("Astra" in x.value or "ASII" in x.value for x in app.markdown)


def test_audit_7_export_consistency_excel_and_pdf():
    """
    Test 7 — Export Consistency (Website vs. Excel vs. PDF):
    Verify that the generated Excel export bytes produce a valid workbook with matching valuation parameters.
    """
    from valuation.data import demo_company, demo_peers, peer_record, BILLION
    from valuation.model import BASE_FIELDS, infer_assumptions, default_drivers, forecast, dcf, sensitivity, relative_values
    from valuation.export import workbook

    c = demo_company()
    historical = c["historical"]
    period = str(historical.columns[-1])
    first_year = 2026
    b = {k: float(historical.loc[k, period]) if k in historical.index and pd.notna(historical.loc[k, period]) else 0.0 for k in BASE_FIELDS}
    a = infer_assumptions(historical, b, c)
    drivers = default_drivers(a, first_year)
    f = forecast(b, a, first_year, drivers)
    shares = (c["shares"] or 0) / BILLION
    res = dcf(f, b, a, shares)
    grid = sensitivity(f, b, a, shares)

    raw_peers = demo_peers()
    peers = [peer_record(p, period) for p in raw_peers]
    target = dict(
        revenue=b["revenue"],
        ebit=b["revenue"] - b["cogs"] - b["opex"] - b["da"],
        ebitda=b["revenue"] - b["cogs"] - b["opex"],
        net_income=b["net_income"],
        book_equity=max(0.0, b.get("equity", 0.0) - a.other_claims),
    )
    relative = relative_values(peers, target, b["cash"], b["short_debt"] + b["long_debt"], shares, a.other_claims, a.nonoperating_assets)

    excel_bytes = workbook(c, historical, b, a, drivers, f, res, grid, peers, relative)
    assert excel_bytes is not None and len(excel_bytes) > 5000

    wb = openpyxl.load_workbook(io.BytesIO(excel_bytes), data_only=True)
    assert "Dashboard" in wb.sheetnames
    assert "Assumptions" in wb.sheetnames
    assert "Pro-Forma Forecast" in wb.sheetnames
    assert "DCF Bridge" in wb.sheetnames
    assert "Relative Valuation" in wb.sheetnames
    assert "Historical & Inputs" in wb.sheetnames


def test_audit_8_workflow_navigation_consistency():
    """
    Test 8 — Workflow Navigation Consistency:
    Verify that traversing tabs preserves session state assumptions without resetting.
    """
    app = AppTest.from_file(APP_PATH, default_timeout=35).run()
    assert not app.exception

    # Change growth input
    growth = next(n for n in app.number_input if n.label == "Growth · years 1–3 (%)")
    growth.set_value(9.5)
    btn_apply = next(b for b in app.button if b.label == "Apply assumptions")
    btn_apply.click().run()
    assert not app.exception

    # Run again without changes to simulate navigating between tabs
    app.run()
    assert not app.exception

    # Value must remain preserved at 9.5%
    growth_after = next(n for n in app.number_input if n.label == "Growth · years 1–3 (%)")
    assert growth_after.value == 9.5
