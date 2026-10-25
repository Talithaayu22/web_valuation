# Nusa: IDX Valuation Workspace
## Deliverable 1 · User Guide & Operating Manual

> **Mid-Term Examination: Digital Business Valuation**  
> **Framework:** Aswath Damodaran & McKinsey Valuation (7th Edition)  
> **Platform Standard:** Highest-Score Implementation (Web-Based Valuation Platform + Dynamic Excel Model + Executive PDF)

---

## 1. Executive Summary & Purpose

**Nusa: The IDX Valuation Workspace** is an institutional-grade, AI-assisted valuation platform engineered specifically for non-financial operating companies listed on the Indonesia Stock Exchange (IDX).

The workstation operationalizes the **Highest-Score Implementation Criteria** of the Digital Business Valuation syllabus by synthesizing three distinct valuation approaches:
1. **Observed Market Valuation (Benchmark, 0% Weight)**: Secondary market price, market capitalization, trailing P/E, EV/EBITDA, and public liquidity.
2. **Intrinsic Discounted Cash Flow (Primary Anchor, 75% Default Weight)**: 5-year explicit pro-forma free cash flow to firm (FCFF) discounted at a rigorously estimated WACC, incorporating Damodaran's sustainable terminal reinvestment constraint.
3. **Relative Comparable Valuation (Market Cross-Check, 25% Default Weight)**: Multiple-derived implied equity cross-check calibrated against comparable peers strictly sharing the official IDX sub-industry classification.

---

## 2. System Architecture & Component Structure

The platform enforces a strict separation between **Data Ingestion**, **Valuation Engine**, **Assumptions Lab**, and **Multi-Channel Presentation**:

```
Project_taliyu/
│
├── app.py                      # Main Streamlit web application & executive user interface
├── USER_GUIDE.md               # Deliverable 1 Operating Manual (this document)
│
├── valuation/                  # Core Modular Financial Valuation Package
│   ├── data.py                 # Sourcing layer: Official IDX Excel registry & Yahoo Finance statements
│   ├── model.py                # Pure mathematical engine: WACC, Pro-Forma forecast, DCF, Multiples, Rules
│   ├── export.py               # Dynamic openpyxl exporter generating formula-driven .xlsx models
│   ├── report_pdf.py           # Institutional 2-page ReportLab PDF equity research generator
│   └── storage.py              # Local SQLite database for persistent scenario storage
│
├── book/                       # Repository Data Store
│   ├── Company LIsted on IDX.xlsx   # Official IDX registry (959 listed companies, sectors, sub-industries)
│   └── Mid Term Description.docx    # Academic requirements and examination rubrics
│
├── standalone_mockup/          # Independent HTML/CSS Presentation Mockup
│   └── idx_valuation_workspace.html # Self-contained HTML interactive prototype for UI/UX review
│
└── tests/                      # Automated Verification & Mathematical Invariant Test Suite
    ├── test_model.py           # 46 financial engine & invariant verification tests
    ├── test_app.py             # 3 UI & session state integration tests
    ├── test_report_pdf.py      # 3 PDF rendering & typography tests
    └── test_export.py          # 1 dynamic Excel formula integrity test (Total: 53 tests)
```

---

## 3. Installation & Setup Instructions

### Prerequisites
- Python 3.10, 3.11, or 3.12 (64-bit recommended)
- Git (for version control and repository synchronization)
- Windows, macOS, or Linux

### Quick-Start Execution
1. **Open Terminal / Command Prompt** in the project directory:
   ```cmd
   cd c:\Users\khair\Downloads\Project_taliyu
   ```
2. **Activate the Virtual Environment**:
   - Windows PowerShell:
     ```powershell
     .\.venv\Scripts\Activate.ps1
     ```
   - Windows Command Prompt:
     ```cmd
     .venv\Scripts\activate.bat
     ```
   - macOS / Linux:
     ```bash
     source .venv/bin/activate
     ```
3. **Launch the Streamlit Web Application**:
   ```cmd
   streamlit run app.py
   ```
4. **Access the Application**:
   Open your browser at **[http://localhost:8501](http://localhost:8501)** (or `http://127.0.0.1:8501`).

---

## 4. Operating Workflow & User Journey

### Step 1: Company Selection & Ingestion
- In the left sidebar, enter any valid Indonesia Stock Exchange ticker (e.g. `SIDO`, `PTBA`, `ICBP`, `UNVR`, `TLKM`, `ASII`).
- Click **Load Company**.
- The platform queries `book/Company LIsted on IDX.xlsx` to lock the official company name, sector, and sub-industry, while fetching audited financial statements, share count, beta, and trading price via `yfinance`.
- *Note:* Alternatively, click **Explore fictional demo** to evaluate the platform using a pre-configured synthetic company.

### Step 2: Statement Audit & Model Health Check (Data Review Tab)
- Navigate to the **Data review** tab.
- Review historical annual balance sheets, income statements, and cash flows.
- **Currency Normalization**: If the company reports in USD (e.g. `ADRO`, `MEDC`), the platform displays live indicative exchange rates and provides an IDR conversion multiplier.
- **Balance Sheet Plug Check**: Inspect the opening balance sheet discrepancy indicator:
  $$\text{Discrepancy} = \text{Total Assets} - (\text{Total Liabilities} + \text{Total Equity})$$
  The platform confirms `Discrepancy == 0.00 bn IDR` and strictly refuses to insert arbitrary plugs.

### Step 3: Assumption Calibration (Valuation Assumptions Tab)
Navigate to the **Valuation assumptions** tab, organized into three distinct operational pillars:

#### Pillar 1: Cost of Capital (CAPM & WACC)
- **Risk-Free Rate ($R_f$)**: Defaults to 6.64% (benchmarked against the 10-Year Indonesian Government Sovereign Bond FR series).
- **Equity Beta ($\beta$)**: Sourced from regression against the IHSG and adjusted using Marshall Blume's mean-reverting formula ($\beta_{\text{adj}} = 0.67\beta + 0.33$).
- **Equity Risk Premium (ERP)**: Sourced from Aswath Damodaran's published NYU Stern data:
  $$\text{Total ERP} = \text{Mature Market ERP } (4.60\%) + \text{Indonesia Country Risk Premium } (2.18\%) = 6.78\%$$
- **Cost of Equity ($K_e$)**:
  $$K_e = R_f + \beta_{\text{adj}} \times \text{Total ERP}$$
- **After-Tax Cost of Debt ($K_{d,\text{after}}$)**:
  $$K_{d,\text{after}} = K_d \times (1 - t)$$
- **WACC**:
  $$\text{WACC} = (W_e \times K_e) + (W_d \times K_{d,\text{after}})$$
- *Analyst Control:* An optional **WACC Override** field is available for manual stress-testing.

#### Pillar 2: Operating Model & Reinvestment
- **Growth Normalization**:
  - *Non-Cyclical Companies*: SIDO, UNVR, ICBP utilize their exact audited multi-year CAGRs.
  - *Cyclical Commodity Companies*: Coal, Oil & Gas, Metals, Copper, and Plantations & Crops (CPO) apply Damodaran's commodity growth normalization (floored at a conservative 3.50% long-term GDP growth rate if historical CAGR is severely depressed).
- **Margin Progression**: First 3 years execute baseline operating margins; years 4 and 5 transition linearly to long-term sustainable competitive margins.
- **CapEx & Working Capital**: Sourced from audited multi-year medians as a percentage of revenue.

#### Pillar 3: Valuation Policy & Terminal Disciplines
- **Perpetual Growth ($g$)**: Bounded at 2.50% (aligned with Bank Indonesia's central inflation target of $2.5\% \pm 1\%$).
- **Sustainable Terminal ROIC**: Enforces Damodaran's steady-state reinvestment identity:
  $$\text{Terminal Reinvestment Rate} = \frac{g}{\text{ROIC}_{\text{terminal}}}$$
  $$\text{Terminal FCFF} = \text{NOPAT}_{6} \times \left(1 - \frac{g}{\text{ROIC}_{\text{terminal}}}\right)$$

### Step 4: Pro-Forma & Valuation Inspection
- **5-Year Model Tab**: Inspect the integrated 3-statement forecast detailing Revenue $\rightarrow$ EBIT $\rightarrow$ NOPAT $\rightarrow$ CapEx $\rightarrow \Delta\text{NWC} \rightarrow$ FCFF.
- **DCF & Sensitivity Tab**: View the Enterprise Value waterfall bridge and inspect the 2D Sensitivity Heatmap Matrix (WACC 9.5%–12.0% vs Perpetual $g$ 2.0%–3.0%).
- **Relative Valuation Tab**: Inspect the sub-industry peer comparison table with automated outlier exclusions, EBITDA margin similarity rankings, and multiple-implied valuations (EV/EBITDA, P/E, P/BV).

### Step 5: Executive Overview & Synthesis (Overview Tab)
- **Model Health Strip**: Immediate visual confirmation of opening balance sheet balance, currency integrity, terminal growth conservatism, peer gating, and solvency.
- **Tri-Pillar Comparison**: Inspect Market Price vs. DCF Fair Value vs. Peer Multiples.
- **Recommendation Banner**:
  - `BUY`: Implied Upside $\ge +15.0\%$
  - `SELL`: Implied Upside $\le -15.0\%$
  - `HOLD`: Implied Upside between $-15.0\%$ and $+15.0\%$
  - `NOT ELIGIBLE`: Flagged when total debt overhang exceeds enterprise value, resulting in underwater intrinsic equity (restructuring risk).

---

## 5. Downloadable Deliverables

The application generates two independent, executive-grade downloadable files:

### 1. Executive PDF Report (`[Download PDF Report]`)
- Formatted as a high-density, 2-page institutional equity research note.
- Contains company metadata, Tri-Pillar synthesis, 5-year pro-forma forecast table, DCF waterfall, peer group multiples table, transparent decision rules, and AI assistance disclosure.
- Ready for immediate submission or executive briefing.

### 2. Dynamic Formula-Driven Excel Model (`[Export Excel (.xlsx)]`)
- Built via `openpyxl` across 8 structured worksheets:
  1. `Dashboard`: Executive command center with live cross-sheet formulas, Model Health checks, and dynamic `IF()` recommendation logic.
  2. `Assumptions`: Soft-blue editable input cells for CAPM and operating drivers with live formulas for $K_e$, $K_{d,\text{after}}$, and WACC.
  3. `Pro-Forma Forecast`: 5-year statement projections driven by live Excel formulas for Revenue, EBIT, NOPAT, CapEx, $\Delta\text{NWC}$, and FCFF.
  4. `DCF Bridge`: Live discount factor formulas (`=1 / (1 + WACC)^t`), explicit PV sums (`=SUM(...)`), Damodaran terminal value, and enterprise-to-equity bridge.
  5. `Relative Valuation`: Peer multiples comparison with dynamic `=MEDIAN(...)` and multiple-implied share prices.
  6. `Historical & Inputs`: 3-year audited baseline accounts and balance sheet identity check formula (`=Assets - Claims`).
  7. `Forecast IDR bn` & `Sensitivity IDR`: Complete raw forecast and 2D matrix data tables.
- **Live Recalculation**: Modifying any input cell in Excel immediately updates the pro-forma forecast, DCF equity value, and dashboard recommendation.

---

## 6. Automated Testing & Verification Suite

All mathematical invariants, valuation formulas, and data pipelines are audited via automated pytest suites:

```cmd
cmd /c "set OPENBLAS_NUM_THREADS=1 && set PYTHONPATH=. && .venv\Scripts\pytest.exe --ignore=scratch tests/ -v"
```

### Verified Test Areas (53 Tests Passing)
1. **Balance Sheet Identity**: Total Assets strictly equal Liabilities plus Equity across all historical and projection periods ($0.000000\text{ IDR bn}$ discrepancy).
2. **Cash Flow Reconciliation**: Direct and indirect cash flow statements reconcile with cash balance change ($\Delta\text{Cash}$).
3. **Damodaran Reinvestment Identity**: Terminal FCFF incorporates $(1 - g/\text{ROIC})$ steady-state constraint.
4. **Excel Live Formulas**: Validates that exported `.xlsx` contains real Excel formulas (`SUM`, `IF`, `MEDIAN`, `AVERAGE`) and opens cleanly.
5. **Cyclical Industry Safeguards**: Verifies growth normalization for Energy, Basic Materials, and Plantations & Crops while preserving non-cyclical historical CAGRs.
6. **Official IDX Registry Gating**: Verifies sub-industry matching from `book/Company LIsted on IDX.xlsx`.

---

## 7. Model Boundaries, Scope & Known Limitations

1. **Non-Financial Operating Companies Only**:
   - The platform models non-financial operating businesses.
   - Financial institutions (banks, life insurers, REITs) require specialized equity-cash flow models (e.g. Dividend Discount Models or Free Cash Flow to Equity) and are automatically filtered out.
2. **Yahoo Finance Source Coverage**:
   - Fundamental statements are sourced from Yahoo Finance via `yfinance`. Companies with incomplete disclosure history (e.g. recent IPOs with $< 2$ years of audited statements) will prompt user review in the Data review tab.
3. **No Secondary Equity Dilution Schedule**:
   - Valuation divides equity value by diluted shares outstanding on the valuation date. Forward convertible bond conversions or rights issues should be modeled by overriding diluted shares in the Data review tab.
4. **Local Academic Research Purpose**:
   - Default parameters are provided for academic research and educational evaluation, not formal registered investment advice.

---

## 8. AI Assistance & Governance Disclosure (Deliverable 1 Alignment)

In strict accordance with the **Mid-Term Exam Deliverable 1 & 2 Guidelines**:
- **AI Coding Models Utilized**: Google DeepMind Agentic Coding models (Antigravity architecture).
- **Tasks Supported by AI**:
  - Python application modularization and Streamlit front-end component design.
  - Integration of official IDX Excel company registry (`book/Company LIsted on IDX.xlsx`).
  - Openpyxl dynamic formula generation for live Excel spreadsheet export.
  - ReportLab PDF equity research report compilation.
  - Comprehensive 53-test automated regression suite.
- **Human Verification & Financial Logic Oversight**:
  - Every calculation formula, CAPM input, Damodaran country risk premium, and terminal value identity was manually cross-checked against Aswath Damodaran (*Investment Valuation*, 3rd Ed.) and McKinsey & Company (*Valuation: Measuring and Managing the Value of Companies*, 7th Ed.).
  - 100% of mathematical invariants were formally codified into automated unit tests.
