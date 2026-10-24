# Script to generate the comprehensive, standalone HTML mockup for Gemini
import os

HTML_CONTENT = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Nusa · IDX Valuation Workspace (Mockup for Gemini Redesign)</title>
    <!--
    ========================================================================================
    CONTEXT FOR GEMINI AI / PROMPT DIRECTIVE:
    ----------------------------------------------------------------------------------------
    You are an Elite Financial UI/UX Principal Designer (FactSet / Bloomberg / McKinsey level).
    This HTML file represents "Nusa: The IDX Valuation Workspace", an AI-assisted valuation 
    platform for non-financial companies listed on the Indonesia Stock Exchange (IDX).
    
    ACADEMIC & EXAM OBJECTIVE:
    This application meets the highest-score criteria for an Advanced Digital Business Valuation
    examination (following the Aswath Damodaran & McKinsey Valuation 7th Edition framework).
    The platform synthesizes THREE VALUATION PILLARS:
    1. Observed Market Valuation (Market Price Benchmark, 0% weight)
    2. Intrinsic DCF Valuation (FCFF Fundamental Anchor, 75% default weight)
    3. Relative Peer Valuation (Comparable Multiples Cross-Check, 25% default weight)
    
    CRITICAL TECHNICAL & DATA CONSTRAINTS:
    - DO NOT change financial formulas, calculation logic, or variable names.
    - All model values in pro-forma are in IDR billion; shares in billions; prices in IDR/share.
    - Strictly ZERO emojis or informal emoticons. Use typography, badges, and clean layout cards.
    - Focus on enhancing: visual hierarchy, user-friendliness, interactive clarity, 
      institutional typography, executive appeal, and seamless student/analyst workflows.
    ========================================================================================
    -->
    <style>
        :root {
            --primary-dark: #173e37;
            --primary-teal: #087f69;
            --primary-light: #e3f3ec;
            --bg-page: #f8faf9;
            --surface-card: #ffffff;
            --border-light: #e2e8f0;
            --border-dark: #cbd5e1;
            --text-main: #1e293b;
            --text-muted: #64748b;
            --text-light: #94a3b8;
            --accent-green: #059669;
            --accent-amber: #d97706;
            --accent-red: #dc2626;
            --font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: var(--font-family);
            background-color: var(--bg-page);
            color: var(--text-main);
            line-height: 1.5;
            padding: 24px 32px 64px;
        }

        .container {
            max-width: 1480px;
            margin: 0 auto;
        }

        /* Top Navigation Header */
        .top-nav {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding-bottom: 16px;
            border-bottom: 1px solid var(--border-light);
            margin-bottom: 20px;
        }

        .brand-title {
            font-size: 13px;
            font-weight: 800;
            letter-spacing: 1.5px;
            color: var(--primary-teal);
            text-transform: uppercase;
        }

        .ticker-bar {
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .ticker-input {
            padding: 8px 14px;
            border: 1px solid var(--border-light);
            border-radius: 6px;
            font-size: 13px;
            font-weight: 600;
            color: var(--primary-dark);
            background: #ffffff;
            width: 140px;
        }

        .btn-action {
            padding: 8px 16px;
            border-radius: 6px;
            font-size: 12.5px;
            font-weight: 600;
            cursor: pointer;
            border: 1px solid transparent;
            transition: all 0.15s ease;
            text-decoration: none;
            display: inline-flex;
            align-items: center;
            gap: 6px;
        }

        .btn-primary {
            background-color: var(--primary-teal);
            color: #ffffff;
        }
        .btn-primary:hover {
            background-color: #066754;
        }

        .btn-secondary {
            background-color: #ffffff;
            color: var(--primary-dark);
            border-color: var(--border-light);
        }
        .btn-secondary:hover {
            border-color: var(--primary-teal);
        }

        /* Hero Banner */
        .hero {
            background-color: var(--primary-dark);
            color: #ffffff;
            border-radius: 12px;
            padding: 22px 28px;
            margin-bottom: 16px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .hero-left h1 {
            font-size: 26px;
            font-weight: 700;
            letter-spacing: -0.5px;
            margin-bottom: 4px;
        }

        .hero-left p {
            color: #c2dcd3;
            font-size: 13.5px;
        }

        .hero-badges {
            display: flex;
            gap: 10px;
            align-items: center;
        }

        .badge-pill {
            background: rgba(255, 255, 255, 0.15);
            color: #ffffff;
            padding: 5px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 600;
            letter-spacing: 0.5px;
        }

        /* Model Health & Sanity Audit Strip */
        .model-audit-strip {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            background: #ffffff;
            border: 1px solid var(--border-light);
            border-radius: 8px;
            padding: 9px 14px;
            margin-bottom: 18px;
            align-items: center;
        }

        .audit-label {
            font-size: 11px;
            font-weight: 800;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.6px;
            margin-right: 4px;
        }

        .audit-item {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            font-size: 11.5px;
            color: #4a5568;
            background: #f8fafc;
            border: 1px solid var(--border-light);
            border-radius: 6px;
            padding: 4px 10px;
        }

        .audit-item b {
            color: #1a202c;
            font-weight: 600;
        }

        .audit-dot {
            width: 7px;
            height: 7px;
            border-radius: 50%;
            display: inline-block;
        }

        .audit-item.passed .audit-dot { background-color: var(--primary-teal); }
        .audit-item.warning .audit-dot { background-color: var(--accent-amber); }
        .audit-item.alert .audit-dot { background-color: var(--accent-red); }

        /* Executive Recommendation & Action Banner */
        .rec-banner {
            display: grid;
            grid-template-columns: 1fr 340px;
            gap: 16px;
            background: #ffffff;
            border: 1px solid var(--border-light);
            border-left: 6px solid var(--primary-teal);
            border-radius: 10px;
            padding: 18px 22px;
            margin-bottom: 22px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.02);
            align-items: center;
        }

        .rec-tag {
            font-size: 11px;
            font-weight: 800;
            letter-spacing: 1.2px;
            color: var(--primary-teal);
            text-transform: uppercase;
        }

        .rec-header {
            display: flex;
            align-items: baseline;
            gap: 16px;
            margin: 6px 0 6px;
            flex-wrap: wrap;
        }

        .rec-badge {
            font-size: 26px;
            font-weight: 800;
            color: var(--primary-teal);
        }

        .rec-upside {
            font-size: 15px;
            color: var(--text-main);
        }

        .rec-summary {
            font-size: 13.5px;
            color: #475569;
            line-height: 1.4;
        }

        .rec-actions {
            display: flex;
            flex-direction: column;
            gap: 8px;
            justify-content: center;
        }

        /* Tri-Pillar Valuation Synthesis Grid */
        .section-heading {
            font-size: 17px;
            font-weight: 700;
            color: var(--primary-dark);
            margin: 20px 0 12px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        .tri-pillar-grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 16px;
            margin-bottom: 24px;
        }

        .pillar-card {
            background: var(--surface-card);
            border: 1px solid var(--border-light);
            border-radius: 12px;
            padding: 18px 20px;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            box-shadow: 0 1px 3px rgba(0,0,0,0.02);
            transition: all 0.15s ease;
        }

        .pillar-card:hover {
            border-color: var(--primary-teal);
        }

        .pillar-card-featured {
            border: 1.5px solid var(--primary-teal);
            background: #fcfffd;
            box-shadow: 0 2px 8px rgba(8, 127, 105, 0.06);
        }

        .pillar-tag {
            font-size: 10px;
            font-weight: 800;
            letter-spacing: 0.8px;
            text-transform: uppercase;
            padding: 3px 8px;
            border-radius: 4px;
            display: inline-block;
            margin-bottom: 8px;
            width: fit-content;
        }

        .pillar-tag-market { background: #f1f5f9; color: #475569; }
        .pillar-tag-dcf { background: var(--primary-light); color: var(--primary-teal); }
        .pillar-tag-rel { background: #e6f4f1; color: #2a6256; }

        .pillar-title {
            font-size: 14.5px;
            font-weight: 700;
            color: var(--primary-dark);
            margin-bottom: 2px;
        }

        .pillar-price {
            font-size: 1.65rem;
            font-weight: 800;
            color: var(--primary-dark);
            margin: 4px 0 10px;
            line-height: 1.15;
        }

        .pillar-unit {
            font-size: 11px;
            font-weight: 500;
            color: var(--text-muted);
        }

        .pillar-metrics {
            border-top: 1px solid #f1f5f9;
            padding-top: 9px;
            margin-bottom: 10px;
            display: flex;
            flex-direction: column;
            gap: 6px;
        }

        .p-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 12px;
            color: var(--text-muted);
        }

        .p-row b {
            color: #1e293b;
            font-weight: 600;
        }

        .pillar-footer {
            font-size: 11px;
            color: var(--text-muted);
            border-top: 1px dashed var(--border-light);
            padding-top: 8px;
            margin-top: auto;
        }

        /* Tabs Navigation */
        .tabs-header {
            display: flex;
            gap: 4px;
            border-bottom: 1px solid var(--border-light);
            margin-bottom: 20px;
            overflow-x: auto;
        }

        .tab-btn {
            padding: 10px 18px;
            font-size: 13.5px;
            font-weight: 600;
            color: var(--text-muted);
            background: none;
            border: none;
            border-bottom: 2px solid transparent;
            cursor: pointer;
            transition: all 0.15s ease;
            white-space: nowrap;
        }

        .tab-btn:hover {
            color: var(--primary-teal);
        }

        .tab-btn.active {
            color: var(--primary-teal);
            border-bottom-color: var(--primary-teal);
        }

        .tab-content {
            display: none;
        }

        .tab-content.active {
            display: block;
        }

        /* Tables & Cards */
        .card {
            background: #ffffff;
            border: 1px solid var(--border-light);
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 20px;
        }

        .card-header {
            font-size: 14px;
            font-weight: 700;
            color: var(--primary-dark);
            margin-bottom: 12px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        table.data-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 12.5px;
            text-align: left;
        }

        table.data-table th {
            background: #f8fafc;
            color: var(--text-muted);
            font-weight: 700;
            padding: 9px 12px;
            border-bottom: 1px solid var(--border-light);
            text-transform: uppercase;
            font-size: 11px;
            letter-spacing: 0.5px;
        }

        table.data-table td {
            padding: 8px 12px;
            border-bottom: 1px solid #f1f5f9;
            color: var(--text-main);
        }

        table.data-table tr:hover td {
            background-color: #fbfdfc;
        }

        table.data-table td.num {
            text-align: right;
            font-variant-numeric: tabular-nums;
            font-weight: 500;
        }

        /* 3-Column Assumptions Form Layout */
        .assumptions-grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 18px;
        }

        .form-group {
            margin-bottom: 14px;
        }

        .form-group label {
            display: block;
            font-size: 11.5px;
            font-weight: 700;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 4px;
        }

        .form-control {
            width: 100%;
            padding: 8px 12px;
            border: 1px solid var(--border-light);
            border-radius: 6px;
            font-size: 13px;
            color: var(--text-main);
            background: #ffffff;
        }

        .form-caption {
            font-size: 11px;
            color: var(--text-light);
            margin-top: 3px;
        }

        /* Footer */
        .footer {
            margin-top: 48px;
            padding-top: 20px;
            border-top: 1px solid var(--border-light);
            font-size: 12px;
            color: var(--text-muted);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        /* Football Field Visual Simulation */
        .football-bar {
            height: 28px;
            border-radius: 4px;
            background: rgba(8, 127, 105, 0.2);
            position: relative;
            margin: 8px 0;
            display: flex;
            align-items: center;
        }

        .football-marker {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            background: var(--primary-teal);
            position: absolute;
            top: 9px;
            transform: translateX(-50%);
        }
    </style>
</head>
<body>

<div class="container">

    <!-- COMPONENT: TOP NAVIGATION & CONTROLS -->
    <header class="top-nav">
        <div class="brand-title">Nusa · The IDX Valuation Workspace</div>
        <div class="ticker-bar">
            <span style="font-size: 12px; color: var(--text-muted); font-weight: 600;">Ticker:</span>
            <input type="text" class="ticker-input" value="SIDO.JK" readonly>
            <button class="btn-action btn-secondary" onclick="alert('Ticker SIDO loaded from official IDX Excel repository')">Change Ticker</button>
            <button class="btn-action btn-secondary">Explore Demo</button>
        </div>
    </header>

    <!-- COMPONENT: HERO BANNER (Live Synchronized with IDX Excel Registry) -->
    <section class="hero">
        <div class="hero-left">
            <h1>PT Industri Jamu dan Farmasi Sido Muncul Tbk.</h1>
            <p>Healthcare &nbsp;/&nbsp; Pharmaceuticals &nbsp;·&nbsp; Fiscal-Year-End Valuation Convention</p>
        </div>
        <div class="hero-badges">
            <div class="badge-pill">SIDO.JK</div>
            <div class="badge-pill">OFFICIAL IDX REGISTRY</div>
            <div class="badge-pill">YAHOO FINANCIAL STATEMENTS</div>
        </div>
    </section>

    <!-- COMPONENT: REAL-TIME MODEL HEALTH & SANITY STRIP (Mid-Term Exam Rubric) -->
    <section class="model-audit-strip">
        <span class="audit-label">Model Health:</span>
        <div class="audit-item passed">
            <span class="audit-dot"></span>
            <span>Balance Sheet: <b>Balanced (0.00 bn plug)</b></span>
        </div>
        <div class="audit-item passed">
            <span class="audit-dot"></span>
            <span>Currency: <b>IDR (Live Verified)</b></span>
        </div>
        <div class="audit-item passed">
            <span class="audit-dot"></span>
            <span>Terminal g: <b>2.50% (&le; GDP Growth)</b></span>
        </div>
        <div class="audit-item passed">
            <span class="audit-dot"></span>
            <span>Peer Universe: <b>3 Gated (Pharmaceuticals)</b></span>
        </div>
        <div class="audit-item passed">
            <span class="audit-dot"></span>
            <span>Capital Structure: <b>Solvent (Intrinsic Equity &gt; 0)</b></span>
        </div>
    </section>

    <!-- COMPONENT: EXECUTIVE RECOMMENDATION & ACTION BANNER -->
    <section class="rec-banner">
        <div>
            <div class="rec-tag">INVESTMENT RECOMMENDATION · MID-TERM DECISION CRITERIA</div>
            <div class="rec-header">
                <span class="rec-badge">BUY</span>
                <span class="rec-upside">Implied Upside: <b>+30.1%</b> &nbsp;|&nbsp; Margin of Safety: <b>23.1%</b></span>
            </div>
            <div class="rec-summary">
                Target valuation is derived from a transparent blend: <b>75.0% Intrinsic DCF</b> (fundamental cash flow anchor) + <b>25.0% Relative Valuation</b> (calibrated against 3 sub-industry peers KLBF, TSPC, KAEF).
            </div>
        </div>
        <div class="rec-actions">
            <button class="btn-action btn-primary" style="justify-content: center;" onclick="alert('Downloading Executive PDF Report...')">
                Download PDF Report
            </button>
            <button class="btn-action btn-secondary" style="justify-content: center;" onclick="alert('Exporting Pro-Forma Excel Workbook...')">
                Export Excel (.xlsx)
            </button>
        </div>
    </section>

    <!-- COMPONENT: TRI-PILLAR VALUATION SYNTHESIS GRID -->
    <div class="section-heading">
        <span>Valuation Synthesis · Tri-Pillar Comparison</span>
        <span style="font-size: 12px; color: var(--text-muted); font-weight: 500;">Blended Target: <b>IDR 445 / share</b></span>
    </div>

    <section class="tri-pillar-grid">
        <!-- Pillar 1: Market Valuation -->
        <div class="pillar-card">
            <div>
                <div class="pillar-tag pillar-tag-market">PILLAR 1 · BENCHMARK (0% WEIGHT)</div>
                <div class="pillar-title">Observed Market Price</div>
                <div class="pillar-price">Rp 342 <span class="pillar-unit">/ share</span></div>
            </div>
            <div class="pillar-metrics">
                <div class="p-row"><span>Market Cap</span><b>Rp 10,068.5 bn</b></div>
                <div class="p-row"><span>Trailing P/E</span><b>8.8x</b></div>
                <div class="p-row"><span>EV / EBITDA</span><b>6.2x</b></div>
                <div class="p-row"><span>Diluted Shares</span><b>29.44 bn</b></div>
            </div>
            <div class="pillar-footer">Weight: <b>0.0%</b> · Observed Public Price</div>
        </div>

        <!-- Pillar 2: Intrinsic DCF (FCFF) -->
        <div class="pillar-card pillar-card-featured">
            <div>
                <div class="pillar-tag pillar-tag-dcf">PILLAR 2 · INTRINSIC ANCHOR (75% WEIGHT)</div>
                <div class="pillar-title">DCF Valuation (FCFF)</div>
                <div class="pillar-price" style="color: var(--primary-teal);">Rp 456 <span class="pillar-unit">/ share</span></div>
            </div>
            <div class="pillar-metrics">
                <div class="p-row"><span>Base Case (50%)</span><b>Rp 456</b></div>
                <div class="p-row"><span>Bear Case (25%)</span><b>Rp 392</b></div>
                <div class="p-row"><span>Bull Case (25%)</span><b>Rp 528</b></div>
                <div class="p-row"><span>WACC · Terminal g</span><b>10.88% · 2.50%</b></div>
            </div>
            <div class="pillar-footer" style="color: var(--primary-teal);">Weight: <b>75.0%</b> · Primary Fundamental Anchor</div>
        </div>

        <!-- Pillar 3: Relative Valuation -->
        <div class="pillar-card">
            <div>
                <div class="pillar-tag pillar-tag-rel">PILLAR 3 · MARKET CROSS-CHECK (25% WEIGHT)</div>
                <div class="pillar-title">Relative Valuation</div>
                <div class="pillar-price" style="color: #2a6256;">Rp 412 <span class="pillar-unit">/ share</span></div>
            </div>
            <div class="pillar-metrics">
                <div class="p-row"><span>Lower Quartile (P25)</span><b>Rp 365</b></div>
                <div class="p-row"><span>Upper Quartile (P75)</span><b>Rp 468</b></div>
                <div class="p-row"><span>Gated Peers</span><b>3 Peers (KLBF, TSPC, KAEF)</b></div>
                <div class="p-row"><span>Multiples Applied</span><b>EV/EBITDA, P/E, P/BV</b></div>
            </div>
            <div class="pillar-footer" style="color: #2a6256;">Weight: <b>25.0%</b> · Sub-Industry Calibrated</div>
        </div>
    </section>

    <!-- COMPONENT: INTERACTIVE WORKSPACE TABS -->
    <nav class="tabs-header">
        <button class="tab-btn active" onclick="switchTab(event, 'tab-overview')">Overview</button>
        <button class="tab-btn" onclick="switchTab(event, 'tab-assumptions')">Valuation assumptions</button>
        <button class="tab-btn" onclick="switchTab(event, 'tab-model')">5-year model</button>
        <button class="tab-btn" onclick="switchTab(event, 'tab-dcf')">DCF & sensitivity</button>
        <button class="tab-btn" onclick="switchTab(event, 'tab-peers')">Relative valuation</button>
        <button class="tab-btn" onclick="switchTab(event, 'tab-data')">Data review</button>
    </nav>

    <!-- ==================== TAB 1: OVERVIEW ==================== -->
    <div id="tab-overview" class="tab-content active">
        <!-- Football Field Valuation Range -->
        <div class="card">
            <div class="card-header">
                <span>Valuation Range Comparison (Football Field Analysis)</span>
                <span style="font-size: 12px; color: var(--text-muted);">Central Blended Fair Value: Rp 445</span>
            </div>
            <div style="margin: 16px 0;">
                <div style="font-size: 12px; font-weight: 600; color: var(--text-muted); margin-bottom: 4px;">DCF (FCFF) Range (Rp 392 – Rp 528)</div>
                <div class="football-bar" style="width: 70%; margin-left: 20%;">
                    <div class="football-marker" style="left: 48%;"></div>
                </div>

                <div style="font-size: 12px; font-weight: 600; color: var(--text-muted); margin-bottom: 4px;">Relative Valuation Range P25–P75 (Rp 365 – Rp 468)</div>
                <div class="football-bar" style="width: 55%; margin-left: 15%; background: rgba(42, 98, 86, 0.2);">
                    <div class="football-marker" style="left: 45%; background: #2a6256;"></div>
                </div>

                <div style="font-size: 12px; font-weight: 600; color: var(--text-muted); margin-bottom: 4px;">Market Reference Price (Rp 342)</div>
                <div class="football-bar" style="width: 30%; margin-left: 10%; background: rgba(100, 116, 139, 0.2);">
                    <div class="football-marker" style="left: 50%; background: #64748b;"></div>
                </div>
            </div>
        </div>

        <!-- Transparent Decision Rules -->
        <div class="card">
            <div class="card-header">Valuation Approach Selection & Weight Justification (Rule 1 & Rule 2)</div>
            <p style="font-size: 13px; color: var(--text-main); margin-bottom: 10px;">
                <b>Methodology Rationale:</b> Robust operating history, positive cash generation, and 3 validated sub-industry peers justify a 75% DCF fundamental anchor and 25% relative multiple cross-check.
            </p>
            <div style="font-size: 12.5px; color: var(--text-muted); line-height: 1.6;">
                • <b>Rule 1 (Intrinsic Fundamental Anchor):</b> DCF (FCFF) is given primary emphasis (75%) because it measures the fundamental capacity of Sido Muncul to generate operating cash flows independently of short-term market sentiment or sector pricing bubbles.<br>
                • <b>Rule 2 (Peer Quality Calibration):</b> Relative valuation provides a secondary cross-check (25%) because &ge;2 comparable peers sharing the official IDX sub-industry (Healthcare / Pharmaceuticals) meet financial similarity criteria (EBITDA margin distance &lt; 15%, DER distance &lt; 60%).
            </div>
        </div>
    </div>

    <!-- ==================== TAB 2: VALUATION ASSUMPTIONS ==================== -->
    <div id="tab-assumptions" class="tab-content">
        <div class="card">
            <div class="card-header">Three-Pillar Valuation Assumptions Lab</div>
            <div class="assumptions-grid">
                <!-- Pillar 1: Cost of Capital -->
                <div>
                    <h3 style="font-size: 13px; font-weight: 700; color: var(--primary-teal); margin-bottom: 12px; text-transform: uppercase;">
                        Pillar 1: Cost of Capital (WACC)
                    </h3>
                    <div class="form-group">
                        <label>Risk-Free Rate Rf (%)</label>
                        <input type="number" class="form-control" value="6.75">
                        <div class="form-caption">10-year Indonesia Government Bond yield</div>
                    </div>
                    <div class="form-group">
                        <label>Blume-Adjusted Beta</label>
                        <input type="number" class="form-control" value="0.75">
                        <div class="form-caption">Regressed against IHSG and mean-reverted</div>
                    </div>
                    <div class="form-group">
                        <label>Total Equity Risk Premium (%)</label>
                        <input type="number" class="form-control" value="7.25">
                        <div class="form-caption">Mature ERP (4.60%) + Damodaran Indonesia CRP (2.65%)</div>
                    </div>
                    <div class="form-group">
                        <label>Pre-Tax Borrowing Cost Kd (%)</label>
                        <input type="number" class="form-control" value="7.50">
                    </div>
                    <div class="form-group">
                        <label>Target Debt Weight Wd (%)</label>
                        <input type="number" class="form-control" value="10.0">
                    </div>
                </div>

                <!-- Pillar 2: Operating Model -->
                <div>
                    <h3 style="font-size: 13px; font-weight: 700; color: var(--primary-teal); margin-bottom: 12px; text-transform: uppercase;">
                        Pillar 2: Operating Drivers
                    </h3>
                    <div class="form-group">
                        <label>Revenue Growth Y1–3 (%)</label>
                        <input type="number" class="form-control" value="8.50">
                        <div class="form-caption">Exact audited 3-year historical CAGR (Non-Cyclical)</div>
                    </div>
                    <div class="form-group">
                        <label>Mature Revenue Growth Y5 (%)</label>
                        <input type="number" class="form-control" value="5.00">
                    </div>
                    <div class="form-group">
                        <label>Operating Margin Y1–3 (%)</label>
                        <input type="number" class="form-control" value="38.20">
                    </div>
                    <div class="form-group">
                        <label>Mature Operating Margin Y5 (%)</label>
                        <input type="number" class="form-control" value="35.00">
                    </div>
                    <div class="form-group">
                        <label>CapEx % of Revenue</label>
                        <input type="number" class="form-control" value="4.50">
                    </div>
                </div>

                <!-- Pillar 3: Scenarios & Policy -->
                <div>
                    <h3 style="font-size: 13px; font-weight: 700; color: var(--primary-teal); margin-bottom: 12px; text-transform: uppercase;">
                        Pillar 3: Policy & Scenarios
                    </h3>
                    <div class="form-group">
                        <label>Terminal Growth Rate g (%)</label>
                        <input type="number" class="form-control" value="2.50">
                        <div class="form-caption">Anchored to Bank Indonesia central inflation target</div>
                    </div>
                    <div class="form-group">
                        <label>Sustainable Terminal ROIC (%)</label>
                        <input type="number" class="form-control" value="20.00">
                        <div class="form-caption">Determines sustainable reinvestment rate (g / ROIC)</div>
                    </div>
                    <div class="form-group">
                        <label>DCF Weight in Blended Target (%)</label>
                        <input type="number" class="form-control" value="75.0">
                    </div>
                    <div class="form-group">
                        <label>Relative Weight in Blended Target (%)</label>
                        <input type="number" class="form-control" value="25.0">
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- ==================== TAB 3: 5-YEAR PRO-FORMA MODEL ==================== -->
    <div id="tab-model" class="tab-content">
        <div class="card">
            <div class="card-header">5-Year Integrated Financial Statement Forecast (IDR Billion)</div>
            <table class="data-table">
                <thead>
                    <tr>
                        <th>Line Item</th>
                        <th class="num">2024A (Base)</th>
                        <th class="num">2025E (Y1)</th>
                        <th class="num">2026E (Y2)</th>
                        <th class="num">2027E (Y3)</th>
                        <th class="num">2028E (Y4)</th>
                        <th class="num">2029E (Y5)</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td><b>Revenue</b></td>
                        <td class="num">3,566.2</td>
                        <td class="num">3,869.3</td>
                        <td class="num">4,198.2</td>
                        <td class="num">4,555.1</td>
                        <td class="num">4,860.3</td>
                        <td class="num">5,103.3</td>
                    </tr>
                    <tr>
                        <td>Revenue Growth (%)</td>
                        <td class="num">—</td>
                        <td class="num">8.5%</td>
                        <td class="num">8.5%</td>
                        <td class="num">8.5%</td>
                        <td class="num">6.7%</td>
                        <td class="num">5.0%</td>
                    </tr>
                    <tr>
                        <td>Operating Profit (EBIT)</td>
                        <td class="num">1,362.3</td>
                        <td class="num">1,478.1</td>
                        <td class="num">1,603.7</td>
                        <td class="num">1,740.1</td>
                        <td class="num">1,778.9</td>
                        <td class="num">1,786.2</td>
                    </tr>
                    <tr>
                        <td>Operating Margin (%)</td>
                        <td class="num">38.2%</td>
                        <td class="num">38.2%</td>
                        <td class="num">38.2%</td>
                        <td class="num">38.2%</td>
                        <td class="num">36.6%</td>
                        <td class="num">35.0%</td>
                    </tr>
                    <tr>
                        <td>NOPAT (EBIT &times; [1 - Tax])</td>
                        <td class="num">1,062.6</td>
                        <td class="num">1,152.9</td>
                        <td class="num">1,250.9</td>
                        <td class="num">1,357.2</td>
                        <td class="num">1,387.5</td>
                        <td class="num">1,393.2</td>
                    </tr>
                    <tr>
                        <td>CapEx (Reinvestment)</td>
                        <td class="num">(160.5)</td>
                        <td class="num">(174.1)</td>
                        <td class="num">(188.9)</td>
                        <td class="num">(205.0)</td>
                        <td class="num">(218.7)</td>
                        <td class="num">(229.6)</td>
                    </tr>
                    <tr>
                        <td>Change in NWC (&Delta;NWC)</td>
                        <td class="num">(42.1)</td>
                        <td class="num">(45.5)</td>
                        <td class="num">(49.3)</td>
                        <td class="num">(53.5)</td>
                        <td class="num">(45.8)</td>
                        <td class="num">(36.5)</td>
                    </tr>
                    <tr style="background: #f8fafc; font-weight: 700;">
                        <td><b>Free Cash Flow to Firm (FCFF)</b></td>
                        <td class="num">—</td>
                        <td class="num"><b>1,018.3</b></td>
                        <td class="num"><b>1,099.7</b></td>
                        <td class="num"><b>1,187.7</b></td>
                        <td class="num"><b>1,214.0</b></td>
                        <td class="num"><b>1,220.1</b></td>
                    </tr>
                </tbody>
            </table>
        </div>
    </div>

    <!-- ==================== TAB 4: DCF VALUATION & SENSITIVITY ==================== -->
    <div id="tab-dcf" class="tab-content">
        <div class="card">
            <div class="card-header">Enterprise-to-Equity Valuation Bridge (IDR Billion)</div>
            <table class="data-table">
                <tbody>
                    <tr><td>Present Value of Explicit Forecast Cash Flows (Years 1–5)</td><td class="num"><b>Rp 4,382.4 bn</b></td></tr>
                    <tr><td>Present Value of Terminal Value (at 10.88% WACC, 2.50% g)</td><td class="num"><b>Rp 8,624.1 bn</b></td></tr>
                    <tr style="background: #f8fafc; font-weight: 700;"><td><b>Operating Enterprise Value (EV)</b></td><td class="num"><b>Rp 13,006.5 bn</b></td></tr>
                    <tr><td>(+) Cash &amp; Liquid Marketable Securities</td><td class="num">+ Rp 842.1 bn</td></tr>
                    <tr><td>(+) Non-Operating Assets</td><td class="num">+ Rp 120.0 bn</td></tr>
                    <tr><td>(&minus;) Total Interest-Bearing Debt</td><td class="num">&minus; Rp 215.3 bn</td></tr>
                    <tr><td>(&minus;) Minority &amp; Other Non-Controlling Claims</td><td class="num">&minus; Rp 0.0 bn</td></tr>
                    <tr style="background: #e3f3ec; font-weight: 800; color: var(--primary-teal);"><td><b>Intrinsic Equity Value</b></td><td class="num"><b>Rp 13,753.3 bn</b></td></tr>
                    <tr><td>Diluted Shares Outstanding</td><td class="num">29.44 bn shares</td></tr>
                    <tr style="font-size: 15px; font-weight: 800; color: var(--primary-dark);"><td><b>DCF Fair Value per Share</b></td><td class="num"><b>Rp 456 / share</b></td></tr>
                </tbody>
            </table>
        </div>

        <div class="card">
            <div class="card-header">2D Sensitivity Heatmap Matrix: WACC vs. Perpetual Growth (IDR/Share)</div>
            <table class="data-table" style="text-align: center;">
                <thead>
                    <tr>
                        <th>Terminal g \ WACC</th>
                        <th class="num">9.50%</th>
                        <th class="num">10.00%</th>
                        <th class="num">10.88% (Base)</th>
                        <th class="num">11.50%</th>
                        <th class="num">12.00%</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td><b>2.00%</b></td>
                        <td class="num">Rp 512</td>
                        <td class="num">Rp 480</td>
                        <td class="num">Rp 435</td>
                        <td class="num">Rp 408</td>
                        <td class="num">Rp 388</td>
                    </tr>
                    <tr style="background: #fcfffd; font-weight: 700;">
                        <td><b>2.50% (Base)</b></td>
                        <td class="num">Rp 542</td>
                        <td class="num">Rp 506</td>
                        <td class="num" style="color: var(--primary-teal); background: #e3f3ec;"><b>Rp 456</b></td>
                        <td class="num">Rp 426</td>
                        <td class="num">Rp 404</td>
                    </tr>
                    <tr>
                        <td><b>3.00%</b></td>
                        <td class="num">Rp 578</td>
                        <td class="num">Rp 537</td>
                        <td class="num">Rp 481</td>
                        <td class="num">Rp 448</td>
                        <td class="num">Rp 423</td>
                    </tr>
                </tbody>
            </table>
        </div>
    </div>

    <!-- ==================== TAB 5: RELATIVE VALUATION & PEERS ==================== -->
    <div id="tab-peers" class="tab-content">
        <div class="card">
            <div class="card-header">Sub-Industry Peer Group Intelligence (Healthcare / Pharmaceuticals)</div>
            <table class="data-table">
                <thead>
                    <tr>
                        <th>Ticker</th>
                        <th>Company Name</th>
                        <th class="num">Price</th>
                        <th class="num">EV/EBITDA</th>
                        <th class="num">P/E</th>
                        <th class="num">P/BV</th>
                        <th class="num">EBITDA Margin</th>
                        <th>Similarity</th>
                    </tr>
                </thead>
                <tbody>
                    <tr style="background: #e3f3ec; font-weight: 700;">
                        <td>SIDO.JK</td>
                        <td>PT Industri Jamu dan Farmasi Sido Muncul Tbk. (Target)</td>
                        <td class="num">342</td>
                        <td class="num">6.2x</td>
                        <td class="num">8.8x</td>
                        <td class="num">2.9x</td>
                        <td class="num">41.2%</td>
                        <td>TARGET</td>
                    </tr>
                    <tr>
                        <td>KLBF.JK</td>
                        <td>PT Kalbe Farma Tbk.</td>
                        <td class="num">1,480</td>
                        <td class="num">12.4x</td>
                        <td class="num">21.8x</td>
                        <td class="num">3.4x</td>
                        <td class="num">16.5%</td>
                        <td>High (88%)</td>
                    </tr>
                    <tr>
                        <td>TSPC.JK</td>
                        <td>PT Tempo Scan Pacific Tbk.</td>
                        <td class="num">2,150</td>
                        <td class="num">6.8x</td>
                        <td class="num">10.4x</td>
                        <td class="num">1.4x</td>
                        <td class="num">14.1%</td>
                        <td>High (84%)</td>
                    </tr>
                    <tr>
                        <td>KAEF.JK</td>
                        <td>PT Kimia Farma Tbk.</td>
                        <td class="num">680</td>
                        <td class="num">9.1x</td>
                        <td class="num">14.2x</td>
                        <td class="num">1.8x</td>
                        <td class="num">8.9%</td>
                        <td>Medium (72%)</td>
                    </tr>
                </tbody>
            </table>
        </div>
    </div>

    <!-- ==================== TAB 6: DATA REVIEW ==================== -->
    <div id="tab-data" class="tab-content">
        <div class="card">
            <div class="card-header">Historical Audited Financial Statement Base &amp; Balance Sheet Reconciliation</div>
            <table class="data-table">
                <thead>
                    <tr>
                        <th>Account</th>
                        <th class="num">Reported (IDR bn)</th>
                        <th class="num">Model Input (IDR bn)</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody>
                    <tr><td>Total Assets</td><td class="num">3,891.2</td><td class="num">3,891.2</td><td>Audited 2024</td></tr>
                    <tr><td>Total Liabilities</td><td class="num">491.5</td><td class="num">491.5</td><td>Audited 2024</td></tr>
                    <tr><td>Total Stockholders' Equity</td><td class="num">3,399.7</td><td class="num">3,399.7</td><td>Audited 2024</td></tr>
                    <tr style="background: #e3f3ec; font-weight: 700;">
                        <td><b>Balance Sheet Plug Discrepancy (base_check)</b></td>
                        <td class="num"><b>0.00</b></td>
                        <td class="num"><b>0.00</b></td>
                        <td><b>PASSED (Zero Discrepancy)</b></td>
                    </tr>
                </tbody>
            </table>
        </div>
    </div>

    <!-- COMPONENT: ACADEMIC GOVERNANCE FOOTER (Mid-Term Exam Deliverable 1) -->
    <footer class="footer">
        <div>
            <b>NUSA · IDX VALUATION LAB</b> &nbsp;|&nbsp; McKinsey &amp; Damodaran Framework &nbsp;|&nbsp; Local Research Workspace
        </div>
        <div>
            AI Assistance &amp; Model Governance Compliant &nbsp;|&nbsp; 100% Invariants Verified
        </div>
    </footer>

</div>

<!-- Interactive Tab Switcher Script -->
<script>
    function switchTab(evt, tabId) {
        const tabContents = document.getElementsByClassName("tab-content");
        for (let i = 0; i < tabContents.length; i++) {
            tabContents[i].classList.remove("active");
        }
        const tabBtns = document.getElementsByClassName("tab-btn");
        for (let i = 0; i < tabBtns.length; i++) {
            tabBtns[i].classList.remove("active");
        }
        document.getElementById(tabId).classList.add("active");
        evt.currentTarget.classList.add("active");
    }
</script>

</body>
</html>
"""

def generate():
    target_dir = os.path.abspath("standalone_mockup")
    os.makedirs(target_dir, exist_ok=True)
    target_path = os.path.join(target_dir, "idx_valuation_workspace.html")
    with open(target_path, "w", encoding="utf-8") as f:
        f.write(HTML_CONTENT)
    print(f"Standalone HTML generated successfully at: {target_path}")

if __name__ == "__main__":
    generate()
