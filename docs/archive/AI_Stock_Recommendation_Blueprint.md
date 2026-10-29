# ARCHITECTURAL SPECIFICATION & IMPLEMENTATION BLUEPRINT: AI-DRIVEN STOCK & SMALL-CAP ("GEM") RECOMMENDATION ENGINE

> **Sketch — superseded.** This file is not the product contract and not the build plan.
>
> Implement against [northstar.md](northstar.md) and [decision_layer_plan.md](decision_layer_plan.md). Ideas here that contradict those docs are **rejected**, including: Redis, GraphQL, FMP/Polygon, `user_id` UUIDs, OpenAI as the writer, Piotroski F-Score / Altman Z as screens or hard gates (F ≥ 7), ΔSharpe > 0.05 cuts, LLM-owned entry/target/stop, and a “Gema Moat Score.”
>
> Product language is named desk metrics (EV/EBITDA, 5y percentile, FCF yield, net debt / EBITDA, EBITDA growth, trap, accrual badge). Keep this file only as historical sketch.

## 1. SYSTEM OVERVIEW & EXECUTIVE SUMMARY

This document specifies the end-to-end architecture, quantitative pipelines, data ingestion workflows, and UI/UX design patterns for an advanced, context-aware AI Stock Recommendation Engine.

The platform evolves traditional static market dashboards into an actionable investment decision platform. It integrates:
1. **User Portfolio Context**: Personalizing recommendations based on Sharpe ratio impact, covariance matrix calculations, sector concentration, and risk metrics.
2. **Quantitative Pre-Filtering**: Processing SEC EDGAR JSON data and market metrics using deterministic mathematical scoring (Piotroski F-Score, Altman Z-Score, Multiples).
3. **Qualitative AI Reasoning**: Extracting material changes from SEC 10-K, 10-Q, and Form 4 filings via direct LLM context windows (eliminating unnecessary RAG overhead for structured forms).
4. **"Gems" / Small-Cap Discovery Module**: A specialized pipeline targeting high-growth, financially sound small-cap equities ($300M–$2B market cap).

---

## 2. HIGH-LEVEL SYSTEM ARCHITECTURE

```
                                  [DATA SOURCES]
                 ┌──────────────────────┬──────────────────────┐
                 │                      │                      │
         SEC EDGAR API          Market Data APIs        User Portfolio
       (Company Facts JSON,     (Prices, Ratios,           (Holdings,
         Submissions, XBRL)        Benchmark Data)        Cash, Weights)
                 │                      │                      │
                 └──────────────────────┼──────────────────────┘
                                        │
                                        ▼
                  ┌──────────────────────────────────────────┐
                  │ 1. DATA INGESTION & SCREENING ENGINE     │
                  │    (Async Batch Worker / Redis Cache)    │
                  └─────────────────────┬────────────────────┘
                                        │
                                        ▼
                  ┌──────────────────────────────────────────┐
                  │ 2. QUANTITATIVE & PORTFOLIO ENGINE       │
                  │    - Piotroski F-Score & Altman Z-Score  │
                  │    - Covariance & Correlation Matrix     │
                  │    - Marginal Risk & Sharpe Impact       │
                  └─────────────────────┬────────────────────┘
                                        │
                                        ▼
                  ┌──────────────────────────────────────────┐
                  │ 3. AGENTIC AI REASONING ENGINE           │
                  │    - SEC 10-K/10-Q Section Extractor     │
                  │    - Insider Trading (Form 4) Parser     │
                  │    - Trade Blueprint & Thesis Generator  │
                  └─────────────────────┬────────────────────┘
                                        │
                                        ▼
                  ┌──────────────────────────────────────────┐
                  │ 4. FASTAPI / REST & GRAPHQL API LAYER    │
                  │    (Serves Cache / Persists to PostgreSQL)│
                  └─────────────────────┬────────────────────┘
                                        │
                                        ▼
                  ┌──────────────────────────────────────────┐
                  │ 5. INTERACTIVE DASHBOARD / FRONTEND UI   │
                  │    - Portfolio Fit Match Score           │
                  │    - Trade Execution Blueprint           │
                  │    - Small-Cap "Gems" Explorer           │
                  └──────────────────────────────────────────┘
```

---

## 3. CORE CORE ENGINE & DATA PIPELINES

### 3.1 Data Ingestion Strategy
* **SEC EDGAR API (100% Free)**:
  * Headers: Custom `User-Agent: YourAppName/1.0 (contact@yourapp.com)`
  * Endpoints:
    * `https://data.sec.gov/api/xbrl/companyfacts/CIK{cik.zfill(10)}.json` (Financial Statements)
    * `https://data.sec.gov/submissions/CIK{cik.zfill(10)}.json` (Form 4 & 10-K/10-Q metadata)
* **Market Data APIs** (e.g., Financial Modeling Prep / Yahoo Finance / Polygon): Real-time/EOD prices, volume, valuation multiples.

### 3.2 Quantitative Pre-Filtering (Piotroski F-Score Engine)
Before sending data to the LLM, equities are filtered using deterministic financial health metrics.

**Piotroski F-Score Criteria (9-Point Scale):**
1. **Profitability**:
   * Positive Return on Assets ($ROA > 0$) $ightarrow$ +1
   * Positive Operating Cash Flow ($CFO > 0$) $ightarrow$ +1
   * Quality of Earnings ($CFO > ROA$) $ightarrow$ +1
   * Change in ROA ($\Delta ROA > 0$) $ightarrow$ +1
2. **Leverage, Liquidity, & Funds**:
   * Decrease in Long-term Debt ($\Delta Debt < 0$) $ightarrow$ +1
   * Increase in Current Ratio ($\Delta CR > 0$) $ightarrow$ +1
   * No Shares Dilution (Shares Issued $\le 0$) $ightarrow$ +1
3. **Operating Efficiency**:
   * Increase in Gross Margin ($\Delta GM > 0$) $ightarrow$ +1
   * Increase in Asset Turnover ($\Delta AssetTurnover > 0$) $ightarrow$ +1

*Threshold*: Stock candidates must score **F-Score $\ge 7$** to qualify for AI Thesis Generation.

### 3.3 Small-Cap "Gems" Screening Rules
Target Universe: Market Cap **\$300M to \$2B**.
* **Revenue Growth**: YoY Revenue Growth $> 15\%$.
* **Free Cash Flow**: Positive FCF Yield ($FCF / EV > 4\%$).
* **Solvency**: Total Debt to Equity $< 0.5$.
* **Insider Alignment**: Insider Ownership $> 10\%$.
* **Institutional Accumulation**: Increasing institutional holdings quarter-over-quarter (via Form 13F metadata).

---

## 4. PORTFOLIO MATCHING & IMPACT EVALUATOR

When a user has an active portfolio, candidates are evaluated for **Portfolio Fit** rather than standalone performance.

### 4.1 Quantitative Metrics Calculated
1. **Covariance & Correlation ($ho$)**:
   $$ho_{i, p} = rac{	ext{Cov}(R_i, R_p)}{\sigma_i \sigma_p}$$
   *Goal*: Minimize portfolio concentration by penalizing assets with $ho > 0.75$ against core holdings.
2. **Marginal Contribution to Risk (MCR)**:
   $$	ext{MCR}_i = rac{(\Sigma w)_i}{\sigma_p}$$
   Evaluates how adding candidate asset $i$ alters overall volatility.
3. **Sharpe Ratio Impact**:
   $$\Delta 	ext{Sharpe} = 	ext{Sharpe}_{	ext{new}} - 	ext{Sharpe}_{	ext{current}}$$
   Accept candidate if $\Delta 	ext{Sharpe} > 0.05$.

### 4.2 Two-Path Recommendation Logic
* **Path A: User HAS Portfolio**:
  * Prioritize assets that optimize the Efficient Frontier, reduce sector overlap, or hedge macro exposure.
* **Path B: User DOES NOT HAVE Portfolio**:
  * Provide General Market Alpha based on F-Score, Momentum, and Sector Risk-On/Risk-Off status.

---

## 5. AGENTIC AI & SEC REASONING ENGINE

### 5.1 No-RAG Parsing Architecture
Instead of heavy vector database indexing (RAG) for SEC filings:
1. Parse 10-K / 10-Q HTML using Python (`BeautifulSoup` or `sec-api` parsing).
2. Extract **Item 1A (Risk Factors)** and **Item 7 (MD&A)** directly.
3. Pass extracted text directly into LLM long-context windows (~128k context) for high accuracy and lower cost.
4. Parse Form 4 XML directly using standard Python XML parsers to detect insider purchases/sales.

### 5.2 Structured Output Prompt Schema
LLMs must return strict JSON schemas containing:
```json
{
  "ticker": "AAPL",
  "thesis_bullets": [
    "Macro Alignment: Benefiting from rate pause",
    "Valuation: Trading at 18x P/E vs 24x sector average",
    "Catalyst: Earnings report in 12 days with upward revisions"
  ],
  "risk_factors": ["Supply chain concentration in Southeast Asia"],
  "insider_activity_summary": "CFO bought $250k in shares over the last 14 days",
  "trade_blueprint": {
    "action": "BUY",
    "suggested_allocation_pct": 3.5,
    "entry_price": 182.50,
    "target_price": 210.00,
    "stop_loss": 171.00,
    "time_horizon": "3-6 months"
  }
}
```

---

## 6. DATA MODELS & DATABASE SCHEMA (PostgreSQL)

```sql
-- User Portfolios
CREATE TABLE user_portfolios (
    user_id UUID PRIMARY KEY,
    cash_balance NUMERIC(15, 2) DEFAULT 0.00,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE portfolio_holdings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES user_portfolios(user_id),
    ticker VARCHAR(10) NOT NULL,
    shares NUMERIC(12, 4) NOT NULL,
    average_buy_price NUMERIC(10, 2) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Quantitative Metrics Cache
CREATE TABLE stock_quant_metrics (
    ticker VARCHAR(10) PRIMARY KEY,
    piotroski_f_score INT CHECK (piotroski_f_score BETWEEN 0 AND 9),
    altman_z_score NUMERIC(6, 2),
    pe_ratio NUMERIC(10, 2),
    ev_ebitda NUMERIC(10, 2),
    fcf_yield NUMERIC(6, 4),
    revenue_growth_yoy NUMERIC(6, 4),
    debt_to_equity NUMERIC(6, 4),
    market_cap NUMERIC(15, 2),
    is_gem CANDIDATE BOOLEAN DEFAULT FALSE,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Generated AI Recommendations
CREATE TABLE ai_recommendations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker VARCHAR(10) NOT NULL,
    user_id UUID REFERENCES user_portfolios(user_id) ON DELETE CASCADE,
    fit_score INT CHECK (fit_score BETWEEN 0 AND 100),
    recommendation_type VARCHAR(20) CHECK (recommendation_type IN ('REBALANCE', 'HEDGE', 'ALPHA', 'GEM')),
    thesis_bullets JSONB NOT NULL,
    trade_blueprint JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

---

## 7. UI / UX SPECIFICATION

### 7.1 Recommendation Card / Ticker Fiche Layout
Each recommendation in the UI should be rendered with 4 clear visual zones:

1. **Header & Portfolio Fit**:
   * Ticker, Company Name, Price, and **Fit Score Badge** (e.g., `92% Portfolio Fit`).
   * Diversification Impact pill (e.g., *"Reduces Tech exposure by 7%"*).
2. **AI Investment Thesis**:
   * 3 concise bullet points outlining the core drivers (Macro, Valuation, Catalyst).
3. **Interactive Trade Blueprint**:
   * Suggested Action (Buy/Sell/Rotate), Entry Price, Target Price, Stop Loss, and Suggested Position Size.
4. **SEC & Insider Signals**:
   * Insider Purchase Tracker (Form 4 status) and Risk Flag indicators.

### 7.2 Small-Cap "Gems" Explorer
* **Gems Grid**: Filterable cards displaying high-growth small-cap opportunities.
* **Gema Moat Score**: Visual 1-100 gauge indicating competitive advantage.
* **Insider Tracker Badge**: Highlight active buying from executives within the past 90 days.

---

## 8. STEP-BY-STEP IMPLEMENTATION ROADMAP

### Phase 1: Core Infra & Quantitative Pipeline
* [ ] Implement Python script for SEC EDGAR `companyfacts` API ingestion.
* [ ] Build Piotroski F-Score and Altman Z-Score calculation module.
* [ ] Setup PostgreSQL database schema and Redis caching layer.
* [ ] Implement Small-Cap Screener rules in SQL / Pandas.

### Phase 2: Portfolio Engine & Matching Math
* [ ] Build portfolio correlation matrix and risk calculation service.
* [ ] Create portfolio fit scoring algorithm ($\Delta 	ext{Sharpe}$, covariance penalty).
* [ ] Implement fallback path for portfolio-less users.

### Phase 3: SEC Parsing & LLM Agent Integration
* [ ] Develop SEC 10-K/10-Q Item 1A & Item 7 HTML parser.
* [ ] Implement Form 4 XML parser for insider transaction aggregation.
* [ ] Integrate OpenAI/Claude API with structured JSON output schema for Thesis & Blueprint generation.

### Phase 4: API & Frontend Integration
* [ ] Expose FastAPI REST endpoints for recommendations, portfolio CRUD, and Gems explorer.
* [ ] Build UI components for Recommendation Fiche and Gems Discovery tab in Next.js / React.
* [ ] Add "Explainable AI" drawer displaying raw SEC inputs and metric calculations.
