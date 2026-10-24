from io import BytesIO
import openpyxl
import pandas as pd
from valuation.data import demo_company, demo_peers, peer_record, BILLION
from valuation.model import (
    BASE_FIELDS, infer_assumptions, default_drivers, forecast, dcf, sensitivity, relative_values
)
from valuation.export import workbook


def test_dynamic_excel_export_structure_and_formulas():
    c = demo_company()
    historical = c["historical"]
    period = str(historical.columns[-1])
    first_year = pd.Timestamp(period).year + 1
    
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
    
    # Load back with openpyxl
    wb = openpyxl.load_workbook(BytesIO(excel_bytes), data_only=False)
    sheet_names = wb.sheetnames
    
    # 1. Verify all 6 core sheets are present
    expected_sheets = [
        "Dashboard", "Assumptions", "Pro-Forma Forecast", "DCF Bridge", "Relative Valuation", "Historical & Inputs"
    ]
    for s in expected_sheets:
        assert s in sheet_names, f"Missing sheet: {s}"
        
    # 2. Verify Dashboard formulas
    ws_dash = wb["Dashboard"]
    assert str(ws_dash["C26"].value).startswith("="), f"Expected formula in Dashboard C26, got: {ws_dash['C26'].value}"
    assert str(ws_dash["C28"].value).startswith("="), f"Expected formula in Dashboard C28, got: {ws_dash['C28'].value}"
    assert "IF" in str(ws_dash["C30"].value), f"Expected IF formula in Dashboard C30, got: {ws_dash['C30'].value}"
    
    # 3. Verify Assumptions formulas
    ws_ass = wb["Assumptions"]
    assert str(ws_ass["C11"].value).startswith("="), f"Expected formula in Assumptions C11 (ERP), got: {ws_ass['C11'].value}"
    assert str(ws_ass["C12"].value).startswith("="), f"Expected formula in Assumptions C12 (Ke), got: {ws_ass['C12'].value}"
    assert str(ws_ass["C18"].value).startswith("="), f"Expected formula in Assumptions C18 (WACC), got: {ws_ass['C18'].value}"
    
    # 4. Verify Pro-Forma Forecast formulas
    ws_pf = wb["Pro-Forma Forecast"]
    assert str(ws_pf["D6"].value).startswith("="), f"Expected formula in Pro-Forma D6 (Revenue), got: {ws_pf['D6'].value}"
    assert str(ws_pf["D17"].value).startswith("="), f"Expected formula in Pro-Forma D17 (FCFF), got: {ws_pf['D17'].value}"
    
    # 5. Verify DCF Bridge formulas
    ws_dcf = wb["DCF Bridge"]
    assert "SUM" in str(ws_dcf["C11"].value), f"Expected SUM formula in DCF Bridge C11, got: {ws_dcf['C11'].value}"
    assert str(ws_dcf["C24"].value).startswith("="), f"Expected formula in DCF Bridge C24 (EV), got: {ws_dcf['C24'].value}"
    assert str(ws_dcf["C29"].value).startswith("="), f"Expected formula in DCF Bridge C29 (Equity), got: {ws_dcf['C29'].value}"
    assert str(ws_dcf["C31"].value).startswith("="), f"Expected formula in DCF Bridge C31 (Price/sh), got: {ws_dcf['C31'].value}"
    
    # 6. Verify Relative Valuation formulas
    ws_rel = wb["Relative Valuation"]
    # Check that MEDIAN exists
    has_median = any("MEDIAN" in str(ws_rel.cell(row=r, column=c).value) for r in range(5, 20) for c in range(2, 10))
    assert has_median, "Expected MEDIAN formula in Relative Valuation"
    
    # 7. Verify Historical & Inputs balance sheet check formula
    ws_hist = wb["Historical & Inputs"]
    assert str(ws_hist["C17"].value).startswith("="), f"Expected formula in Historical C17 (Identity check), got: {ws_hist['C17'].value}"
