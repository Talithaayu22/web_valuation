"""valuation/ui_table.py — Institutional Apple iOS-Inspired Financial Table Renderer.

Provides a unified, clean, and highly readable table rendering engine for
the Nusa IDX Valuation Lab.
"""

from typing import Any, Dict, List, Optional, Tuple, Union
import html
import re
import pandas as pd


def format_period_header(col_key: Any) -> Tuple[str, str]:
    """
    Transforms raw fiscal date strings or timestamps into clean two-tier headers.
    Example: '2022-12-31' or Timestamp('2022-12-31') -> ('FY2022', '2022-12-31')
    If already formatted like 'FY2022', preserves it.
    """
    col_str = str(col_key).strip()
    # Match YYYY-MM-DD or YYYY
    date_match = re.match(r"^(\d{4})(?:-(\d{2})-(\d{2}))?", col_str)
    if date_match:
        year = date_match.group(1)
        sub = col_str if len(col_str) > 4 else f"{year} Annual"
        return f"FY{year}", sub
    if col_str.isdigit() and len(col_str) == 4:
        return f"FY{col_str}", f"{col_str} Annual"
    return col_str, ""


def format_cell_value(val: Any, num_format: str = "{:,.2f}", na_rep: str = "—") -> Tuple[str, str]:
    """
    Formats an individual cell value and determines its alignment class ('col-num' or 'col-text').
    Returns (formatted_string, css_class).
    """
    if val is None or pd.isna(val):
        return na_rep, "col-num col-dim" if na_rep == "—" else "col-text"
    
    # Booleans
    if isinstance(val, (bool,)):
        return ("True" if val else "False"), "col-center"

    # Numeric (int, float)
    if isinstance(val, (int, float)):
        # Handle exact zero
        if abs(val) < 1e-12:
            return "0.00" if "2f" in num_format else "0", "col-num"
        try:
            formatted = num_format.format(val)
            # Parentheses for negative if applicable or standard minus
            return formatted, "col-num"
        except Exception:
            return str(val), "col-num"

    # Strings
    s_val = str(val).strip()
    if s_val == "" or s_val.lower() in ("nan", "none", "null", "missing"):
        return na_rep, "col-num col-dim"

    # String with numeric percentage or multiple like '12.5%' or '1.45x'
    if re.match(r"^[-+]?[\d,]+(?:\.\d+)?(?:%|x|bn|M|k)?$", s_val):
        return s_val, "col-num"

    return html.escape(s_val), "col-text"


def render_apple_table(
    df: pd.DataFrame,
    title: Optional[str] = None,
    unit_label: Optional[str] = None,
    highlight_rows: Optional[List[str]] = None,
    subtotal_rows: Optional[List[str]] = None,
    final_rows: Optional[List[str]] = None,
    category_rows: Optional[Dict[str, str]] = None,
    col_formats: Optional[Dict[str, str]] = None,
    default_format: str = "{:,.2f}",
    na_rep: str = "—",
    max_height: Optional[str] = None,
    sticky_header: bool = True,
    col_alignments: Optional[Dict[str, str]] = None,
    badge_cols: Optional[Dict[str, Dict[str, str]]] = None,
    is_transposed_periods: bool = False,
    hide_index: bool = False,
) -> str:
    """
    Renders a pandas DataFrame as a clean, institutional Apple iOS-style HTML table.
    """
    if df is None or df.empty:
        return '<div class="fin-table-container" style="padding:20px; text-align:center; color:#6E6E73;">No table data available.</div>'

    highlight_set = set(highlight_rows or [])
    subtotal_set = set(subtotal_rows or [])
    final_set = set(final_rows or [])
    category_dict = category_rows or {}
    col_fmt_dict = col_formats or {}
    col_align_dict = col_alignments or {}
    badge_dict = badge_cols or {}

    total_cols = len(df.columns) if hide_index else len(df.columns) + 1

    lines = []
    lines.append('<div class="fin-table-container">')

    # Optional Title & Unit Context Bar
    if title or unit_label:
        lines.append('  <div class="fin-table-header-bar">')
        lines.append(f'    <div class="fin-table-title">{html.escape(title or "")}</div>')
        lines.append(f'    <div class="fin-table-unit">{html.escape(unit_label or "")}</div>')
        lines.append('  </div>')

    # Scrollable Table Body
    scroll_style = f"max-height:{max_height}; " if max_height else ""
    lines.append(f'  <div class="fin-table-scroll" style="{scroll_style}">')
    lines.append('    <table class="fin-table">')

    # Header Row
    lines.append('      <thead>')
    lines.append('        <tr>')
    if not hide_index:
        idx_label = str(df.index.name) if df.index.name else "Line Item / Metric"
        lines.append(f'          <th class="col-label">{html.escape(idx_label)}</th>')

    for col in df.columns:
        c_str = str(col)
        # Determine alignment class
        align_cls = col_align_dict.get(c_str)
        if not align_cls:
            if is_transposed_periods or pd.api.types.is_numeric_dtype(df[col]):
                align_cls = "col-num"
            else:
                align_cls = "col-text"

        if is_transposed_periods:
            main_h, sub_h = format_period_header(col)
            sub_html = f'<div class="th-sub">{html.escape(sub_h)}</div>' if sub_h else ""
            lines.append(f'          <th class="{align_cls}"><div class="th-main">{html.escape(main_h)}</div>{sub_html}</th>')
        else:
            lines.append(f'          <th class="{align_cls}"><div class="th-main">{html.escape(c_str)}</div></th>')

    lines.append('        </tr>')
    lines.append('      </thead>')
    lines.append('      <tbody>')

    # Rows
    for idx_val, row in df.iterrows():
        idx_key = str(idx_val)

        # Check for Category Section Header insertion
        if idx_key in category_dict:
            cat_title = category_dict[idx_key]
            lines.append(f'        <tr class="row-category"><td colspan="{total_cols}">{html.escape(cat_title)}</td></tr>')

        # Determine Row Styling Class
        row_cls = ""
        if idx_key in final_set:
            row_cls = "row-final"
        elif idx_key in subtotal_set:
            row_cls = "row-subtotal"
        elif idx_key in highlight_set:
            row_cls = "row-major"

        row_attr = f' class="{row_cls}"' if row_cls else ""
        lines.append(f'        <tr{row_attr}>')

        # Index Cell
        if not hide_index:
            lines.append(f'          <td class="col-label">{html.escape(idx_key)}</td>')

        # Column Cells
        for col in df.columns:
            c_str = str(col)
            val = row[col]
            num_fmt = col_fmt_dict.get(c_str, default_format)

            # Check if this column uses badges
            if c_str in badge_dict:
                v_str = str(val).strip()
                b_map = badge_dict[c_str]
                badge_type = b_map.get(v_str, "info")
                badge_cls = f"fin-badge fin-badge-{badge_type}"
                lines.append(f'          <td class="col-center"><span class="{badge_cls}">{html.escape(v_str)}</span></td>')
            else:
                formatted_text, cell_cls = format_cell_value(val, num_fmt, na_rep)
                # Override alignment if explicitly defined
                if c_str in col_align_dict:
                    cell_cls = col_align_dict[c_str]
                lines.append(f'          <td class="{cell_cls}">{formatted_text}</td>')

        lines.append('        </tr>')

    lines.append('      </tbody>')
    lines.append('    </table>')
    lines.append('  </div>')
    lines.append('</div>')

    return "\n".join(lines)
