from streamlit.testing.v1 import AppTest
from pathlib import Path


def test_demo_renders_and_assumptions_update():
    app = AppTest.from_file(Path(__file__).resolve().parents[1]/"app.py",default_timeout=30).run()
    assert not app.exception
    assert any("Telkom" in x.value or "TLKM" in x.value or "Nusantara" in x.value for x in app.markdown)
    original = next(m.value for m in app.metric if m.label == "DCF value / share")
    growth = next(n for n in app.number_input if n.label == "Growth · years 1–3 (%)")
    growth.set_value(12.)
    next(b for b in app.button if b.label == "Apply assumptions").click().run()
    assert not app.exception
    revised = next(m.value for m in app.metric if m.label == "DCF value / share")
    assert revised != original


def test_save_and_reopen_restores_assumptions(tmp_path,monkeypatch):
    from valuation import storage
    db_file = tmp_path / "analyses.sqlite3"
    monkeypatch.setenv("VALUATION_DB", str(db_file))
    monkeypatch.setattr(storage, "DB", db_file)
    app = AppTest.from_file(Path(__file__).resolve().parents[1]/"app.py",default_timeout=30).run()
    next(n for n in app.number_input if n.label == "Growth · years 1–3 (%)").set_value(11.)
    next(b for b in app.button if b.label == "Apply assumptions").click().run()
    saved_price = next(m.value for m in app.metric if m.label == "DCF value / share")
    next(b for b in app.button if b.label == "Save analysis").click().run()
    assert not app.exception
    app.run()
    next(n for n in app.number_input if n.label == "Growth · years 1–3 (%)").set_value(5.)
    next(b for b in app.button if b.label == "Apply assumptions").click().run()
    next(b for b in app.button if b.label == "Open saved analysis").click().run()
    assert not app.exception
    assert next(n.value for n in app.number_input if n.label == "Growth · years 1–3 (%)") == 11.
    assert next(m.value for m in app.metric if m.label == "DCF value / share") == saved_price


def test_valuation_assumptions_tab_renders_three_pillars():
    app = AppTest.from_file(Path(__file__).resolve().parents[1]/"app.py", default_timeout=30).run()
    assert not app.exception
    tab_labels = [t.label for t in app.tabs]
    assert "Valuation assumptions" in tab_labels
    markdown_texts = " ".join(x.value for x in app.markdown)
    assert "01 · Operating model" in markdown_texts
    assert "02 · Macro & WACC" in markdown_texts
    assert "03 · Valuation policy" in markdown_texts
    assert any(m.label == "Calculated WACC" for m in app.metric)
    assert any(m.label == "Cost of Equity" for m in app.metric)


def test_app_resilience_with_missing_market_quotes():
    app = AppTest.from_file(Path(__file__).resolve().parents[1]/"app.py", default_timeout=30).run()
    assert not app.exception
    # Set price to 0 to simulate missing/unavailable market quote
    price_input = next(n for n in app.number_input if n.label == "Reference market price (IDR/share)")
    price_input.set_value(0.0)
    app.run()
    assert not app.exception
    obs_metric = next(m.value for m in app.metric if m.label == "Observed Reference Market Price")
    assert obs_metric == "Not available"


def test_format_wib_retrieval_and_badge_rendering():
    from valuation.data import format_wib_retrieval
    # 1. ISO UTC timestamp -> WIB (UTC+7)
    full, short = format_wib_retrieval("2026-10-25T10:52:00+00:00")
    assert full == "25 Oct 2026, 17:52 WIB"
    assert short == "25 Oct '26, 17:52 WIB"

    # 2. Demo or illustrative string
    full_demo, short_demo = format_wib_retrieval("Illustrative data, not market data")
    assert full_demo == "Offline Benchmark"
    assert short_demo == "Offline Benchmark"

    # 3. None / empty
    full_none, short_none = format_wib_retrieval(None)
    assert full_none == "Offline Benchmark"

    # 4. AppTest verifies the badge renders inside the app
    app = AppTest.from_file(Path(__file__).resolve().parents[1]/"app.py", default_timeout=30).run()
    assert not app.exception
    rendered_markdown = " ".join(x.value for x in app.markdown)
    assert "retrieval-badge" in rendered_markdown
    assert "Retrieved Data:" in rendered_markdown
    assert "From :" in rendered_markdown

    # 5. Verify company fetched_at is dynamic and non-empty
    active_co = app.session_state.company
    assert "fetched_at" in active_co
    assert str(active_co["fetched_at"]).startswith("202")


def test_dcf_and_relative_valuation_tab_ui_refinements():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=30).run()
    assert not app.exception
    rendered_markdown = " ".join(x.value for x in app.markdown)

    # 1. Symmetrical 4-card KPI grid
    assert "dcf-kpi-grid" in rendered_markdown
    assert "DCF Fair Value / Share" in rendered_markdown
    assert "Enterprise Value (EV)" in rendered_markdown
    assert "Implied Equity Value" in rendered_markdown
    assert "Relative Value / Share" in rendered_markdown

    # 2. Structured Enterprise-to-Equity Value Bridge schedule (A, B, C sections)
    assert "fin-schedule-table" in rendered_markdown
    assert "A. Enterprise Valuation" in rendered_markdown
    assert "B. Enterprise-to-Equity Adjustments" in rendered_markdown
    assert "C. Final Equity Valuation" in rendered_markdown

    # 3. Structured Terminal Economics & Perpetuity Discipline card (A, B, C, D sections)
    assert "A. Forecast &amp; Terminal Parameters" in rendered_markdown
    assert "B. Terminal Value Calculation (IDR billion)" in rendered_markdown
    assert "C. Terminal Value Contribution to EV" in rendered_markdown
    assert "D. Model Validation &amp; Perpetuity Checks" in rendered_markdown

    # 4. Verify no broken raw LaTeX strings inside HTML cards
    assert "($g$)" not in rendered_markdown
    assert "(\\text{ROIC}" not in rendered_markdown
    assert "($\\text{ROIC}" not in rendered_markdown


def test_overview_assumptions_and_risks_cards_refinement():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=30).run()
    assert not app.exception
    rendered_markdown = " ".join(x.value for x in app.markdown)

    # 1. Verify card containers and labels
    assert "ov-card" in rendered_markdown
    assert "LEVEL 3 DRIVERS · KEY VALUATION ASSUMPTIONS" in rendered_markdown
    assert "Core Operating &amp; Discount Drivers" in rendered_markdown
    assert "LEVEL 3 &amp; 4 · KEY RISKS &amp; MODEL LIMITATIONS" in rendered_markdown
    assert "Material Risks &amp; Active Model Boundaries" in rendered_markdown

    # 2. Verify Key Assumptions table structure and metrics
    assert "ov-assump-table" in rendered_markdown
    assert "Revenue Growth (Y1–3 &rarr; Y5)" in rendered_markdown
    assert "EBIT Margin (Y1–3 &rarr; Y5)" in rendered_markdown
    assert "CapEx &amp; Non-Cash NWC / Sales" in rendered_markdown
    assert "Effective WACC" in rendered_markdown
    assert "Terminal Growth &amp; Terminal ROIC" in rendered_markdown
    assert "Approach Weights (DCF / Relative)" in rendered_markdown
    assert "View All Assumptions &rarr;" in rendered_markdown

    # 3. Verify Key Risks structured list and items
    assert "ov-risk-list" in rendered_markdown
    assert "ov-risk-item" in rendered_markdown
    assert "ov-risk-badge" in rendered_markdown
    assert "Terminal Value Exposure" in rendered_markdown
    assert "View All Risks &amp; Audits &rarr;" in rendered_markdown


def test_shared_table_design_system_and_historical_statements():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=30).run()
    assert not app.exception
    rendered_markdown = " ".join(x.value for x in app.markdown)

    # 1. Universal table container and shared table classes
    assert "fin-table-container" in rendered_markdown
    assert "fin-table" in rendered_markdown
    assert "fin-table-header-bar" in rendered_markdown
    assert "fin-table-title" in rendered_markdown
    assert "fin-table-unit" in rendered_markdown

    # 2. Historical financial statements rendered with two-tier headers
    assert "Consolidated Historical Accounts" in rendered_markdown
    assert "Historical Income Statement" in rendered_markdown
    assert "Historical Balance Sheet" in rendered_markdown
    assert "th-main" in rendered_markdown

    # 3. Row hierarchy classes
    assert "row-major" in rendered_markdown
    assert "row-subtotal" in rendered_markdown

    # 4. Status badges in model validation and peer screening
    assert "fin-badge" in rendered_markdown
    assert "fin-badge-pass" in rendered_markdown

    # 5. Comparable peers and scenario analysis tables
    assert "Comparable Peers Screening &amp; Financial Comparability" in rendered_markdown
    assert "Scenario Valuation Matrix &amp; Operating Case Trajectory" in rendered_markdown


def test_opening_inputs_mapping_table_refinement():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=30).run()
    assert not app.exception
    rendered_markdown = " ".join(x.value for x in app.markdown)

    # 1. Audit header bar for opening mapping
    assert "Opening Balance Sheet &amp; Operating Mapping" in rendered_markdown
    assert "Direct" in rendered_markdown
    assert "Calculated" in rendered_markdown

    # 2. Data editor columns check
    mapping_dfs = [df.value for df in app.dataframe if "Key" in getattr(df.value, "columns", [])]
    assert len(mapping_dfs) > 0
    de_df = mapping_dfs[0]
    assert list(de_df.columns) == ["Key", "Account", "Reported", "Value", "Type", "Source"]
    assert "revenue" in list(de_df["Key"])
    assert "ppe" in list(de_df["Key"])
    assert "cogs" in list(de_df["Key"])
    assert "Revenue" in list(de_df["Account"])


def test_tri_pillar_kpi_card_compact_height_and_scoped_styling():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=30).run()
    assert not app.exception
    rendered_markdown = " ".join(x.value for x in app.markdown)

    # 1. Scoped CSS for tri-pillar compact KPI height (approx 100-110px)
    assert ".st-key-tri_pillar_kpi_wrap [data-testid=\"stMetric\"]" in rendered_markdown
    assert "min-height: 104px" in rendered_markdown or "height: 106px" in rendered_markdown
    assert "margin-top: 14px" in rendered_markdown  # gap between KPI card and supporting metric box

    # 2. Tri-pillar metrics present and correctly labeled
    metric_labels = [m.label for m in app.metric]
    assert "Reference price" in metric_labels
    assert "DCF value / share" in metric_labels
    assert "Relative value / share" in metric_labels


