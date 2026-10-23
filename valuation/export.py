from io import BytesIO
from dataclasses import asdict
import pandas as pd
from openpyxl.styles import Font, PatternFill, Alignment


def workbook(company, historical, base, assumptions, drivers, forecast, result, grid, peers, relative):
    output = BytesIO()
    sheets = {
        "Summary":pd.DataFrame({"Item":["Company","Ticker","Data retrieved","Historical period","Units","Forecast convention","Nature of export"],
                                "Value":[company["name"],company["symbol"],company["fetched_at"],historical.columns[-1],
                                         "IDR billion; shares billion; prices IDR","Annual year-end; base fiscal year + 1","Calculated values snapshot, not Excel formulas"]}),
        "Historical IDR bn":historical,
        "Opening inputs":pd.Series(base,name="IDR bn").to_frame(),
        "Assumptions":pd.Series(asdict(assumptions),name="Value (rates decimal)").to_frame(),
        "Annual drivers":drivers,
        "Forecast IDR bn":forecast.T,
        "DCF":pd.Series(result,name="Value (money IDR bn)").to_frame(),
        "Sensitivity IDR":grid,
        "Peer inputs":pd.DataFrame(peers),
        "Relative valuation":relative,
    }
    with pd.ExcelWriter(output,engine="openpyxl") as writer:
        for name,frame in sheets.items():
            frame.to_excel(writer,sheet_name=name)
            ws = writer.sheets[name]
            ws.freeze_panes = "B2"
            ws.auto_filter.ref = ws.dimensions
            for cell in ws[1]:
                cell.fill = PatternFill("solid",fgColor="087F69")
                cell.font = Font(color="FFFFFF",bold=True)
            for column in ws.columns:
                letter = column[0].column_letter
                ws.column_dimensions[letter].width = min(55,max(16,max(len(str(c.value or "")) for c in column[:30])+2))
            for row in ws.iter_rows(min_row=2):
                for cell in row:
                    if isinstance(cell.value,(float,int)):
                        cell.number_format = '#,##0.00;[Red](#,##0.00)'
                    cell.alignment = Alignment(vertical="top")
    return output.getvalue()
