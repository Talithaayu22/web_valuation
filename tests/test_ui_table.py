"""tests/test_ui_table.py — Unit Tests for Apple-Inspired Table Renderer."""

import pandas as pd
import pytest
from valuation.ui_table import (
    format_period_header,
    format_cell_value,
    render_apple_table,
    parse_mapping_provenance,
)


def test_parse_mapping_provenance():
    # Direct reported line
    p_type, p_exp = parse_mapping_provenance("Reported: revenue")
    assert p_type == "Direct"
    assert "Revenue" in p_exp

    # Calculated formula line
    p_type, p_exp = parse_mapping_provenance("Calculated: revenue − COGS − D&A − EBIT")
    assert p_type == "Calculated"
    assert "Revenue − (COGS + D&A + EBIT)" in p_exp

    # Complex calculation cleaned up
    p_type, p_exp = parse_mapping_provenance("Calculated: current assets less cash and marketable securities, receivables and inventory")
    assert p_type == "Calculated"
    assert "Current Assets − (Cash + AR + Inv)" in p_exp

    # Override
    p_type, p_exp = parse_mapping_provenance("Reported: revenue", is_override=True)
    assert "Override" in p_type

    # Missing
    p_type, p_exp = parse_mapping_provenance("Missing - enter or explicitly accept zero")
    assert p_type == "Missing"


def test_format_period_header():
    # Full date string
    main_h, sub_h = format_period_header("2024-12-31")
    assert main_h == "FY2024"
    assert sub_h == "2024-12-31"

    # Year only
    main_h, sub_h = format_period_header("2025")
    assert main_h == "FY2025"
    assert sub_h == "2025 Annual"

    # Already formatted or custom
    main_h, sub_h = format_period_header("Metric")
    assert main_h == "Metric"
    assert sub_h == ""


def test_format_cell_value():
    # Numeric
    txt, cls = format_cell_value(1234.567, "{:,.2f}")
    assert txt == "1,234.57"
    assert "col-num" in cls

    # Zero
    txt, cls = format_cell_value(0.0, "{:,.2f}")
    assert txt == "0.00"
    assert "col-num" in cls

    # Missing / None
    txt, cls = format_cell_value(None, na_rep="—")
    assert txt == "—"
    assert "col-dim" in cls

    # String text
    txt, cls = format_cell_value("Operating Cash Flow")
    assert txt == "Operating Cash Flow"
    assert "col-text" in cls

    # Percentage string
    txt, cls = format_cell_value("25.4%")
    assert txt == "25.4%"
    assert "col-num" in cls


def test_render_apple_table_empty():
    res = render_apple_table(pd.DataFrame())
    assert "No table data available" in res


def test_render_apple_table_financial_statement():
    df = pd.DataFrame(
        {
            "2022-12-31": [1000.0, 300.0, 150.0],
            "2023-12-31": [1100.0, 320.0, 160.0],
            "2024-12-31": [1200.0, 350.0, 180.0],
        },
        index=["Revenue", "EBITDA", "Net Income"],
    )

    html_out = render_apple_table(
        df,
        title="Income Statement",
        unit_label="IDR billion",
        is_transposed_periods=True,
        highlight_rows=["Revenue", "Net Income"],
        subtotal_rows=["EBITDA"],
    )

    # Check container and title bar
    assert "fin-table-container" in html_out
    assert "Income Statement" in html_out
    assert "IDR billion" in html_out

    # Check two-tier period headers
    assert "FY2022" in html_out
    assert "2022-12-31" in html_out
    assert "FY2024" in html_out

    # Check row styling
    assert 'class="row-major"' in html_out
    assert 'class="row-subtotal"' in html_out
    assert "1,000.00" in html_out
    assert "1,200.00" in html_out


def test_render_apple_table_badges():
    df = pd.DataFrame([
        {"Check ID": "CHK-01", "Rule": "Balance Identity", "Status": "PASS"},
        {"Check ID": "CHK-02", "Rule": "Debt Rollover", "Status": "FAIL"},
    ])

    html_out = render_apple_table(
        df,
        hide_index=True,
        badge_cols={"Status": {"PASS": "pass", "FAIL": "fail"}},
    )

    assert "fin-badge fin-badge-pass" in html_out
    assert "fin-badge fin-badge-fail" in html_out
    assert "CHK-01" in html_out
    assert "CHK-02" in html_out
