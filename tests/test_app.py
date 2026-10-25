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
