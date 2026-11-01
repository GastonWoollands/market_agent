from __future__ import annotations

import re
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from ingest.sec.errors import SecParseError
from store.canonical import MetricFy, MetricTtm, SecProfile, SecTicker

ALLOWED_EXCHANGES = {
    "NYSE": "NYSE",
    "NEW YORK STOCK EXCHANGE": "NYSE",
    "NASDAQ": "Nasdaq",
    "NYSE AMERICAN": "NYSE American",
    "NYSE MKT": "NYSE American",
    "NYSEAMER": "NYSE American",
}
SKIP_TICKER = re.compile(r"[-.]W(S)?$|[-.]U$|[-.]R$|[-.]WT|/|\^", re.IGNORECASE)
REVENUE_CONCEPTS = (
    ("us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax"),
    ("us-gaap", "Revenues"),
    ("us-gaap", "SalesRevenueNet"),
    ("us-gaap", "RevenueFromContractWithCustomerIncludingAssessedTax"),
    ("ifrs-full", "Revenue"),
)
EBIT_CONCEPTS = (("us-gaap", "OperatingIncomeLoss"), ("ifrs-full", "OperatingIncomeLoss"))
DA_CONCEPTS = (
    ("us-gaap", "DepreciationDepletionAndAmortization"),
    ("us-gaap", "DepreciationAndAmortization"),
    ("us-gaap", "DepreciationAmortizationAndAccretionNet"),
)
DEP_CONCEPTS = (("us-gaap", "Depreciation"),)
INTEREST_CONCEPTS = (
    ("us-gaap", "InterestExpense"),
    ("us-gaap", "InterestExpenseNonoperating"),
    ("us-gaap", "InterestExpenseDebt"),
    ("us-gaap", "InterestAndDebtExpense"),
    ("ifrs-full", "InterestExpense"),
)
AMORT_CONCEPTS = (
    ("us-gaap", "AmortizationOfIntangibleAssets"),
    ("us-gaap", "FiniteLivedIntangibleAssetsAmortizationExpense"),
)
CFO_CONCEPTS = (
    ("us-gaap", "NetCashProvidedByUsedInOperatingActivities"),
    ("us-gaap", "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"),
    ("ifrs-full", "CashFlowsFromUsedInOperatingActivities"),
)
CAPEX_CONCEPTS = (
    ("us-gaap", "PaymentsToAcquirePropertyPlantAndEquipment"),
    ("us-gaap", "PaymentsToAcquireProductiveAssets"),
    ("us-gaap", "PaymentsToAcquireOilAndGasPropertyAndEquipment"),
    ("us-gaap", "PaymentsToAcquireOilAndGasProperty"),
    ("ifrs-full", "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities"),
)
# Totals already include the current portion; `DebtAndCapitalLeaseObligations` also
# includes short-term borrowings. Parts are summed only when no total is tagged.
LONG_DEBT_TOTAL_CONCEPTS = (
    ("us-gaap", "LongTermDebt"),
    ("us-gaap", "LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities"),
)
ALL_DEBT_TOTAL_CONCEPTS = (("us-gaap", "DebtAndCapitalLeaseObligations"),)
DEBT_NONCURRENT_CONCEPTS = (
    ("us-gaap", "LongTermDebtNoncurrent"),
    ("us-gaap", "LongTermDebtAndCapitalLeaseObligations"),
    ("us-gaap", "ConvertibleLongTermNotesPayable"),
    ("us-gaap", "ConvertibleNotesPayable"),
    ("us-gaap", "SeniorLongTermNotes"),
    ("us-gaap", "LongTermNotesPayable"),
)
DEBT_CURRENT_CONCEPTS = (
    ("us-gaap", "LongTermDebtCurrent"),
    ("us-gaap", "LongTermDebtAndCapitalLeaseObligationsCurrent"),
    ("us-gaap", "SeniorNotesCurrent"),
    ("us-gaap", "ConvertibleNotesPayableCurrent"),
)
BALANCE_SHEET_CONCEPTS = (
    ("us-gaap", "Liabilities"),
    ("us-gaap", "LiabilitiesAndStockholdersEquity"),
)
SHORT_DEBT_CONCEPTS = (("us-gaap", "ShortTermBorrowings"),)
CASH_CONCEPTS = (
    ("us-gaap", "CashAndCashEquivalentsAtCarryingValue"),
    ("us-gaap", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"),
)
SHARE_CONCEPTS = (
    ("dei", "EntityCommonStockSharesOutstanding"),
    ("us-gaap", "CommonStockSharesOutstanding"),
)
WEIGHTED_SHARE_CONCEPTS = (
    ("us-gaap", "WeightedAverageNumberOfSharesOutstandingBasic"),
    ("us-gaap", "WeightedAverageNumberOfDilutedSharesOutstanding"),
)
NI_CONCEPTS = (
    ("us-gaap", "NetIncomeLoss"),
    ("us-gaap", "ProfitLoss"),
    ("ifrs-full", "ProfitLoss"),
)
GROSS_PROFIT_CONCEPTS = (("us-gaap", "GrossProfit"), ("ifrs-full", "GrossProfit"))
COGS_CONCEPTS = (
    ("us-gaap", "CostOfGoodsAndServicesSold"),
    ("us-gaap", "CostOfRevenue"),
    ("us-gaap", "CostOfGoodsSold"),
)
ASSETS_CONCEPTS = (("us-gaap", "Assets"), ("ifrs-full", "Assets"))
CURRENT_ASSETS_CONCEPTS = (("us-gaap", "AssetsCurrent"), ("ifrs-full", "CurrentAssets"))
CURRENT_LIAB_CONCEPTS = (
    ("us-gaap", "LiabilitiesCurrent"),
    ("ifrs-full", "CurrentLiabilities"),
)
LTD_CONCEPTS = (
    ("us-gaap", "LongTermDebtNoncurrent"),
    ("us-gaap", "LongTermDebt"),
    ("us-gaap", "LongTermDebtAndCapitalLeaseObligations"),
)
LIABILITIES_CONCEPTS = (("us-gaap", "Liabilities"), ("ifrs-full", "Liabilities"))
LIAB_AND_EQUITY_CONCEPTS = (
    ("us-gaap", "LiabilitiesAndStockholdersEquity"),
    ("ifrs-full", "EquityAndLiabilities"),
)
# Equity incl. minority interest first: L&SE minus it leaves liabilities only.
EQUITY_ALL_CONCEPTS = (
    ("us-gaap", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"),
    ("us-gaap", "StockholdersEquity"),
    ("ifrs-full", "Equity"),
)
DEFERRED_REVENUE_CURRENT_CONCEPTS = (
    ("us-gaap", "ContractWithCustomerLiabilityCurrent"),
    ("us-gaap", "DeferredRevenueCurrent"),
)
RETAINED_CONCEPTS = (
    ("us-gaap", "RetainedEarningsAccumulatedDeficit"),
    ("us-gaap", "RetainedEarnings"),
)
EQUITY_CONCEPTS = (
    ("us-gaap", "StockholdersEquity"),
    ("us-gaap", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"),
    ("ifrs-full", "Equity"),
)
ANNUAL_DAYS = (320, 400)
QUARTER_DAYS = (60, 120)
FY_YEARS = 6
INSTANT_SLACK_DAYS = 45
DEBT_FREE_LOOKBACK_DAYS = 400
TTM_MAX_AGE_DAYS = 548


def pad_cik(value: object) -> str:
    digits = re.sub(r"\D", "", str(value))
    if not digits:
        raise SecParseError("CIK is empty")
    return digits.zfill(10)


def yahoo_symbol(ticker: str) -> str:
    return ticker.strip().upper().replace(".", "-")


def tickers_from_payload(payload: Any, *, exchanges: list[str]) -> list[SecTicker]:
    rows = _ticker_rows(payload)
    wanted = {_norm_exchange(item) for item in exchanges}
    wanted.discard("")
    out: list[SecTicker] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        ticker = str(row.get("ticker") or "").strip().upper()
        exchange = _norm_exchange(str(row.get("exchange") or ""))
        if not ticker or ticker in seen or SKIP_TICKER.search(ticker):
            continue
        if wanted and exchange not in wanted:
            continue
        try:
            cik = pad_cik(row.get("cik") if row.get("cik") is not None else row.get("cik_str"))
        except SecParseError:
            continue
        name = str(row.get("name") or row.get("title") or ticker).strip()[:255]
        seen.add(ticker)
        out.append(SecTicker(cik=cik, ticker=ticker, name=name, exchange=exchange or "US"))
    return out


def profile_from_submissions(payload: Any) -> SecProfile:
    if not isinstance(payload, dict) or payload.get("cik") is None:
        raise SecParseError("submissions payload has no cik")
    raw_sic = str(payload.get("sic") or "").strip()
    description = str(payload.get("sicDescription") or "").strip()
    return SecProfile(
        cik=pad_cik(payload["cik"]),
        sic=int(raw_sic) if raw_sic.isdigit() else None,
        sic_description=description[:255] or None,
    )


def ttm_from_facts(
    payload: dict[str, Any],
    *,
    require_quarters: bool = False,
    through: date | None = None,
) -> MetricTtm | None:
    facts = payload.get("facts")
    if not isinstance(facts, dict):
        return None
    raw_cik = payload.get("cik")
    if raw_cik is None:
        return None
    cik = pad_cik(raw_cik)
    revenue, as_of, method = _flow_ttm(facts, REVENUE_CONCEPTS, through=through)
    if revenue is None or as_of is None:
        return None
    if require_quarters and method != "quarters":
        return None
    # Every component must cover the same window as revenue, or it is dropped.
    ebit = _aligned(_flow_ttm(facts, EBIT_CONCEPTS, through=as_of), as_of)
    da = _da_ttm(facts, as_of)
    ebitda = None
    if ebit is not None and da is not None:
        ebitda = ebit + da
    cfo = _aligned(_flow_ttm(facts, CFO_CONCEPTS, through=as_of), as_of)
    capex = _aligned(_flow_ttm(facts, CAPEX_CONCEPTS, through=as_of), as_of)
    if capex is not None:
        capex = abs(capex)
    fcf = None
    if cfo is not None and capex is not None:
        fcf = cfo - capex
    interest = _aligned(_flow_ttm(facts, INTEREST_CONCEPTS, through=as_of), as_of)
    if interest is not None:
        interest = abs(interest)
    debt = _debt_on(facts, as_of)
    cash = _instant_on(facts, CASH_CONCEPTS, as_of)
    net_debt = None
    if debt is not None and cash is not None:
        net_debt = debt - cash
    shares = _latest_shares(facts, as_of)
    current_liabilities = _instant_on(facts, CURRENT_LIAB_CONCEPTS, as_of)
    total_liabilities = _total_liabilities(facts, as_of)
    return MetricTtm(
        cik=cik,
        as_of=as_of,
        revenue=revenue,
        ebitda=ebitda,
        fcf=fcf,
        cfo=cfo,
        capex=capex,
        ebit=ebit,
        interest_expense=interest,
        net_debt=net_debt,
        shares=shares,
        current_liabilities=current_liabilities,
        total_liabilities=total_liabilities,
        deferred_revenue_current=_instant_on(facts, DEFERRED_REVENUE_CURRENT_CONCEPTS, as_of),
    )


def _total_liabilities(facts: dict[str, Any], as_of: date) -> Decimal | None:
    """`Liabilities`, else liabilities-and-equity minus equity (many filers skip the total)."""
    total = _instant_on(facts, LIABILITIES_CONCEPTS, as_of)
    if total is not None:
        return total
    both = _instant_on(facts, LIAB_AND_EQUITY_CONCEPTS, as_of)
    equity = _instant_on(facts, EQUITY_ALL_CONCEPTS, as_of)
    if both is None or equity is None:
        return None
    return both - equity


def ttm_history_from_facts(
    payload: dict[str, Any],
    *,
    require_quarters: bool = True,
    today: date | None = None,
    years: int = 5,
) -> list[MetricTtm]:
    facts = payload.get("facts")
    if not isinstance(facts, dict):
        return []
    start = (today or date.today()) - timedelta(days=years * 365 + 30)
    out: list[MetricTtm] = []
    seen: set[date] = set()
    for end in _quarter_ends(facts, REVENUE_CONCEPTS):
        if end < start:
            continue
        metric = ttm_from_facts(payload, require_quarters=require_quarters, through=end)
        if metric is None or metric.as_of in seen:
            continue
        seen.add(metric.as_of)
        out.append(metric)
    out.sort(key=lambda item: item.as_of)
    return out


def fy_history_from_facts(
    payload: dict[str, Any],
    *,
    today: date | None = None,
    years: int = FY_YEARS,
) -> list[MetricFy]:
    """Annual 10-K snapshots for Piotroski / Altman. Newest years last."""
    facts = payload.get("facts")
    if not isinstance(facts, dict):
        return []
    raw_cik = payload.get("cik")
    if raw_cik is None:
        return []
    cik = pad_cik(raw_cik)
    start = (today or date.today()) - timedelta(days=years * 365 + 30)
    ends = _annual_ends(
        facts,
        REVENUE_CONCEPTS + NI_CONCEPTS + ASSETS_CONCEPTS,
    )
    out: list[MetricFy] = []
    seen: set[date] = set()
    for end in ends:
        if end < start or end in seen:
            continue
        snapshot = _fy_at(facts, cik, end)
        if snapshot is None:
            continue
        seen.add(end)
        out.append(snapshot)
    out.sort(key=lambda item: item.as_of)
    return out


def _fy_at(facts: dict[str, Any], cik: str, as_of: date) -> MetricFy | None:
    revenue = _annual_flow(facts, REVENUE_CONCEPTS, as_of)
    net_income = _annual_flow(facts, NI_CONCEPTS, as_of)
    cfo = _annual_flow(facts, CFO_CONCEPTS, as_of)
    ebit = _annual_flow(facts, EBIT_CONCEPTS, as_of)
    gross_profit = _annual_flow(facts, GROSS_PROFIT_CONCEPTS, as_of)
    if gross_profit is None and revenue is not None:
        cogs = _annual_flow(facts, COGS_CONCEPTS, as_of)
        if cogs is not None:
            gross_profit = revenue - cogs
    total_assets = _instant_on(facts, ASSETS_CONCEPTS, as_of)
    current_assets = _instant_on(facts, CURRENT_ASSETS_CONCEPTS, as_of)
    current_liabilities = _instant_on(facts, CURRENT_LIAB_CONCEPTS, as_of)
    long_term_debt = _instant_on(facts, LTD_CONCEPTS, as_of)
    total_liabilities = _instant_on(facts, LIABILITIES_CONCEPTS, as_of)
    retained_earnings = _instant_on(facts, RETAINED_CONCEPTS, as_of)
    equity = _instant_on(facts, EQUITY_CONCEPTS, as_of)
    shares = _latest_shares(facts, as_of)
    if all(
        item is None
        for item in (
            revenue,
            net_income,
            cfo,
            gross_profit,
            ebit,
            total_assets,
            current_assets,
            current_liabilities,
            long_term_debt,
            total_liabilities,
            retained_earnings,
            equity,
        )
    ):
        return None
    return MetricFy(
        cik=cik,
        as_of=as_of,
        fiscal_year=as_of.year,
        revenue=revenue,
        net_income=net_income,
        cfo=cfo,
        gross_profit=gross_profit,
        ebit=ebit,
        total_assets=total_assets,
        current_assets=current_assets,
        current_liabilities=current_liabilities,
        long_term_debt=long_term_debt,
        total_liabilities=total_liabilities,
        retained_earnings=retained_earnings,
        equity=equity,
        shares=shares,
    )


def _annual_ends(facts: dict[str, Any], concepts: tuple[tuple[str, str], ...]) -> list[date]:
    ends: set[date] = set()
    lo, hi = ANNUAL_DAYS
    for taxonomy, concept in concepts:
        for days, end, _value in _duration_points(facts, taxonomy, concept):
            if lo <= days <= hi:
                ends.add(end)
    return sorted(ends)


def _annual_flow(
    facts: dict[str, Any],
    concepts: tuple[tuple[str, str], ...],
    as_of: date,
) -> Decimal | None:
    lo, hi = ANNUAL_DAYS
    best: tuple[int, Decimal] | None = None
    for taxonomy, concept in concepts:
        for days, end, value in _duration_points(facts, taxonomy, concept):
            if not (lo <= days <= hi):
                continue
            slack = abs((end - as_of).days)
            if slack > INSTANT_SLACK_DAYS:
                continue
            if best is None or slack < best[0]:
                best = (slack, value)
    return None if best is None else best[1]


def _instant_on(
    facts: dict[str, Any],
    concepts: tuple[tuple[str, str], ...],
    as_of: date,
    *,
    units: tuple[str, ...] = ("USD",),
) -> Decimal | None:
    """First matching concept wins (LTD prefers Noncurrent over the broader total)."""
    for taxonomy, concept in concepts:
        exact: Decimal | None = None
        near: tuple[int, Decimal] | None = None
        for row in _unit_rows(facts, taxonomy, concept, units):
            if row.get("start"):
                continue
            end = _as_date(row.get("end"))
            value = _as_decimal(row.get("val"))
            if end is None or value is None:
                continue
            if end == as_of:
                exact = value
                continue
            slack = (as_of - end).days
            if slack < 0 or slack > INSTANT_SLACK_DAYS:
                continue
            if near is None or slack < near[0]:
                near = (slack, value)
        if exact is not None:
            return exact
        if near is not None:
            return near[1]
    return None


def usable_ttm(metric: MetricTtm) -> bool:
    """EV/EBITDA screen: positive EBITDA, shares, net debt, and a cash-flow TTM."""
    if metric.ebitda is None or metric.ebitda <= 0:
        return False
    if metric.shares is None or metric.shares <= 0:
        return False
    if metric.net_debt is None or metric.fcf is None:
        return False
    return True


def fresh_ttm(
    metric: MetricTtm, *, today: date | None = None, max_age_days: int = TTM_MAX_AGE_DAYS
) -> bool:
    cutoff = (today or date.today()) - timedelta(days=max_age_days)
    return metric.as_of >= cutoff


def _ticker_rows(payload: Any) -> list[Any]:
    if isinstance(payload, dict):
        data = payload.get("data")
        fields = payload.get("fields")
        if isinstance(data, list) and isinstance(fields, list):
            names = [str(item) for item in fields]
            return [dict(zip(names, row, strict=False)) for row in data if isinstance(row, list)]
        if all(str(key).isdigit() for key in payload):
            return list(payload.values())
        if "ticker" in payload:
            return [payload]
    if isinstance(payload, list):
        return payload
    raise SecParseError("unexpected company_tickers_exchange payload")


def _norm_exchange(value: str) -> str:
    key = re.sub(r"\s+", " ", value.strip().upper())
    return ALLOWED_EXCHANGES.get(key, key.title() if key else "")


def _flow_ttm(
    facts: dict[str, Any],
    concepts: tuple[tuple[str, str], ...],
    *,
    through: date | None = None,
) -> tuple[Decimal | None, date | None, str | None]:
    best_q: tuple[date, Decimal] | None = None
    best_a: tuple[date, Decimal] | None = None
    # Merged synonyms first; each concept alone as a fallback when the merge leaves a gap.
    for group in (concepts, *((item,) for item in concepts)):
        picked = _last_quarters(_discrete_quarters(facts, group, through=through), 4)
        if len(picked) == 4 and (best_q is None or picked[0][0] > best_q[0]):
            best_q = (picked[0][0], sum((value for _end, value in picked), Decimal("0")))
    for taxonomy, concept in concepts:
        points = _duration_points(facts, taxonomy, concept)
        if through is not None:
            points = [item for item in points if item[1] <= through]
        annual = [item for item in points if 320 <= item[0] <= 400]
        if annual:
            _span, end, value = annual[0]
            if best_a is None or end > best_a[0]:
                best_a = (end, value)
    if best_q is not None:
        return best_q[1], best_q[0], "quarters"
    if best_a is not None:
        return best_a[1], best_a[0], "annual"
    return None, None, None


def _da_ttm(facts: dict[str, Any], as_of: date) -> Decimal | None:
    """Combined D&A for the window, else depreciation (+ amortization when it lines up)."""
    combined = _aligned(_flow_ttm(facts, DA_CONCEPTS, through=as_of), as_of)
    if combined is not None:
        return combined
    dep = _aligned(_flow_ttm(facts, DEP_CONCEPTS, through=as_of), as_of)
    amort = _aligned(_flow_ttm(facts, AMORT_CONCEPTS, through=as_of), as_of)
    if dep is not None and amort is not None:
        return dep + amort
    return dep if dep is not None else amort


def _duration_spans(
    facts: dict[str, Any], taxonomy: str, concept: str
) -> dict[tuple[date, date], Decimal]:
    """(start, end) → value. The latest filing wins when a period is restated."""
    best: dict[tuple[date, date], tuple[str, Decimal]] = {}
    for row in _unit_rows(facts, taxonomy, concept, ("USD",)):
        start = _as_date(row.get("start"))
        end = _as_date(row.get("end"))
        value = _as_decimal(row.get("val"))
        form = str(row.get("form") or "")
        if start is None or end is None or value is None or end <= start:
            continue
        if not form.startswith(("10-Q", "10-K", "20-F", "40-F")):
            continue
        filed = str(row.get("filed") or "")
        key = (start, end)
        if key not in best or filed >= best[key][0]:
            best[key] = (filed, value)
    return {key: value for key, (_filed, value) in best.items()}


def _duration_points(
    facts: dict[str, Any], taxonomy: str, concept: str
) -> list[tuple[int, date, Decimal]]:
    out: list[tuple[int, date, Decimal]] = []
    for row in _unit_rows(facts, taxonomy, concept, ("USD",)):
        start = _as_date(row.get("start"))
        end = _as_date(row.get("end"))
        value = _as_decimal(row.get("val"))
        form = str(row.get("form") or "")
        if start is None or end is None or value is None:
            continue
        if not form.startswith(("10-Q", "10-K", "20-F", "40-F")):
            continue
        days = (end - start).days
        if days <= 0:
            continue
        out.append((days, end, value))
    out.sort(key=lambda item: item[1], reverse=True)
    return out


def _quarter_ends(facts: dict[str, Any], concepts: tuple[tuple[str, str], ...]) -> list[date]:
    return sorted(_discrete_quarters(facts, concepts))


def _discrete_quarters(
    facts: dict[str, Any],
    concepts: tuple[tuple[str, str], ...],
    *,
    through: date | None = None,
) -> dict[date, Decimal]:
    """Quarter end → three-month value.

    10-Q cash-flow lines are year-to-date and 10-Ks rarely tag Q4, so a quarter is
    either a reported 60–120 day span or the difference of two YTD spans that share
    a start (6M − 3M, 9M − 6M, FY − 9M). Concepts are synonyms in priority order:
    filers switch tags between a 10-Q and the 10-K, so spans are merged first.
    """
    spans: dict[tuple[date, date], Decimal] = {}
    for taxonomy, concept in concepts:
        for key, value in _duration_spans(facts, taxonomy, concept).items():
            spans.setdefault(key, value)
    if through is not None:
        spans = {key: value for key, value in spans.items() if key[1] <= through}
    lo, hi = QUARTER_DAYS
    out: dict[date, Decimal] = {}
    by_start: dict[date, list[tuple[date, Decimal]]] = {}
    for (start, end), value in spans.items():
        if lo <= (end - start).days <= hi:
            out[end] = value
        by_start.setdefault(start, []).append((end, value))
    for rows in by_start.values():
        rows.sort()
        for (prev_end, prev_value), (end, value) in zip(rows, rows[1:], strict=False):
            if end not in out and lo <= (end - prev_end).days <= hi:
                out[end] = value - prev_value
    return out


def _last_quarters(quarters: dict[date, Decimal], count: int) -> list[tuple[date, Decimal]]:
    """Newest `count` quarters, only if each is one quarter before the next (no gaps)."""
    lo, hi = QUARTER_DAYS
    picked: list[tuple[date, Decimal]] = []
    for end in sorted(quarters, reverse=True):
        if picked:
            gap = (picked[-1][0] - end).days
            if gap < lo:
                continue
            if gap > hi:
                break
        picked.append((end, quarters[end]))
        if len(picked) == count:
            break
    return picked


def _aligned(result: tuple[Decimal | None, date | None, str | None], as_of: date) -> Decimal | None:
    value, end, _method = result
    return value if end == as_of else None


def _debt_tagged_since(facts: dict[str, Any], start: date) -> bool:
    concepts = (
        LONG_DEBT_TOTAL_CONCEPTS
        + ALL_DEBT_TOTAL_CONCEPTS
        + DEBT_NONCURRENT_CONCEPTS
        + DEBT_CURRENT_CONCEPTS
        + SHORT_DEBT_CONCEPTS
    )
    for taxonomy, concept in concepts:
        for row in _unit_rows(facts, taxonomy, concept, ("USD",)):
            end = _as_date(row.get("end"))
            value = _as_decimal(row.get("val"))
            if not row.get("start") and end is not None and end >= start and value:
                return True
    return False


def _debt_on(facts: dict[str, Any], as_of: date) -> Decimal | None:
    """Gross debt on the balance-sheet date, never a stale instant and never total + parts."""
    long_term = _instant_on(facts, LONG_DEBT_TOTAL_CONCEPTS, as_of)
    if long_term is None:
        all_debt = _instant_on(facts, ALL_DEBT_TOTAL_CONCEPTS, as_of)
        if all_debt is not None:
            return all_debt
        parts = [
            _instant_on(facts, DEBT_NONCURRENT_CONCEPTS, as_of),
            _instant_on(facts, DEBT_CURRENT_CONCEPTS, as_of),
        ]
        found = [item for item in parts if item is not None]
        long_term = sum(found, Decimal("0")) if found else None
    short = _instant_on(facts, SHORT_DEBT_CONCEPTS, as_of)
    if long_term is None and short is None:
        # Debt-free only with a balance sheet on this date and no debt line for a year.
        # A filer that tagged debt recently and stopped (custom tags) stays unknown.
        if _instant_on(facts, BALANCE_SHEET_CONCEPTS, as_of) is None:
            return None
        if _debt_tagged_since(facts, as_of - timedelta(days=DEBT_FREE_LOOKBACK_DAYS)):
            return None
        return Decimal("0")
    return (long_term or Decimal("0")) + (short or Decimal("0"))


def _latest_shares(facts: dict[str, Any], as_of: date) -> Decimal | None:
    instant = _latest_instant(facts, SHARE_CONCEPTS, as_of, units=("shares", "pure"))
    if instant is not None:
        return instant
    best: tuple[tuple[date, int], Decimal] | None = None
    for taxonomy, concept in WEIGHTED_SHARE_CONCEPTS:
        for row in _unit_rows(facts, taxonomy, concept, ("shares", "pure")):
            start = _as_date(row.get("start"))
            end = _as_date(row.get("end"))
            value = _as_decimal(row.get("val"))
            if end is None or value is None or value <= 0 or end > as_of:
                continue
            days = (end - start).days if start is not None else 90
            score = (end, 1 if 60 <= days <= 120 else 0)
            if best is None or score > best[0]:
                best = (score, value)
    return None if best is None else best[1]


def _latest_instant(
    facts: dict[str, Any],
    concepts: tuple[tuple[str, str], ...],
    as_of: date,
    *,
    units: tuple[str, ...] = ("USD",),
) -> Decimal | None:
    best: tuple[date, Decimal] | None = None
    for taxonomy, concept in concepts:
        for row in _unit_rows(facts, taxonomy, concept, units):
            if row.get("start"):
                continue
            end = _as_date(row.get("end"))
            value = _as_decimal(row.get("val"))
            if end is None or value is None or end > as_of:
                continue
            if best is None or end > best[0]:
                best = (end, value)
    return None if best is None else best[1]


def _unit_rows(
    facts: dict[str, Any], taxonomy: str, concept: str, units: tuple[str, ...]
) -> list[dict[str, Any]]:
    node = facts.get(taxonomy)
    if not isinstance(node, dict):
        return []
    concept_node = node.get(concept)
    if not isinstance(concept_node, dict):
        return []
    unit_map = concept_node.get("units")
    if not isinstance(unit_map, dict):
        return []
    rows: list[dict[str, Any]] = []
    for unit in units:
        raw = unit_map.get(unit)
        if isinstance(raw, list):
            rows.extend(item for item in raw if isinstance(item, dict))
    return rows


def _as_date(value: object) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _as_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
