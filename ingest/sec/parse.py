from __future__ import annotations

import re
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from ingest.sec.errors import SecParseError
from store.canonical import MetricTtm, SecTicker

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
)
DEP_CONCEPTS = (("us-gaap", "Depreciation"),)
AMORT_CONCEPTS = (
    ("us-gaap", "AmortizationOfIntangibleAssets"),
    ("us-gaap", "FiniteLivedIntangibleAssetsAmortizationExpense"),
)
CFO_CONCEPTS = (
    ("us-gaap", "NetCashProvidedByUsedInOperatingActivities"),
    ("ifrs-full", "CashFlowsFromUsedInOperatingActivities"),
)
CAPEX_CONCEPTS = (
    ("us-gaap", "PaymentsToAcquirePropertyPlantAndEquipment"),
    ("ifrs-full", "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities"),
)
DEBT_CONCEPTS = (
    ("us-gaap", "LongTermDebt"),
    ("us-gaap", "LongTermDebtNoncurrent"),
    ("us-gaap", "LongTermDebtCurrent"),
    ("us-gaap", "ShortTermBorrowings"),
)
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
    ebit, _, _ = _flow_ttm(facts, EBIT_CONCEPTS, through=through)
    da, _, _ = _da_ttm(facts, through=through)
    ebitda = None
    if ebit is not None and da is not None:
        ebitda = ebit + da
    cfo, _, _ = _flow_ttm(facts, CFO_CONCEPTS, through=through)
    capex, _, _ = _flow_ttm(facts, CAPEX_CONCEPTS, through=through)
    fcf = None
    if cfo is not None and capex is not None:
        fcf = cfo - abs(capex)
    debt = _sum_instant(facts, DEBT_CONCEPTS, as_of)
    cash = _latest_instant(facts, CASH_CONCEPTS, as_of)
    net_debt = None
    if debt is not None and cash is not None:
        net_debt = debt - cash
    shares = _latest_shares(facts, as_of)
    return MetricTtm(
        cik=cik,
        as_of=as_of,
        revenue=revenue,
        ebitda=ebitda,
        fcf=fcf,
        net_debt=net_debt,
        shares=shares,
    )


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
    for taxonomy, concept in concepts:
        points = _duration_points(facts, taxonomy, concept)
        if through is not None:
            points = [item for item in points if item[1] <= through]
        quarterly = [item for item in points if 60 <= item[0] <= 120]
        picked = _last_quarters(quarterly, 4)
        if len(picked) == 4:
            total = sum((item[2] for item in picked), Decimal("0"))
            end = picked[0][1]
            if best_q is None or end > best_q[0]:
                best_q = (end, total)
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


def _da_ttm(
    facts: dict[str, Any], *, through: date | None = None
) -> tuple[Decimal | None, date | None, str | None]:
    combined = _flow_ttm(facts, DA_CONCEPTS, through=through)
    if combined[0] is not None:
        return combined
    dep = _flow_ttm(facts, DEP_CONCEPTS, through=through)
    amort = _flow_ttm(facts, AMORT_CONCEPTS, through=through)
    if (
        dep[0] is not None
        and amort[0] is not None
        and dep[1] == amort[1]
        and dep[2] == amort[2]
    ):
        return dep[0] + amort[0], dep[1], dep[2]
    if dep[0] is not None:
        return dep
    return amort


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
    ends: set[date] = set()
    for taxonomy, concept in concepts:
        for days, end, _value in _duration_points(facts, taxonomy, concept):
            if 60 <= days <= 120:
                ends.add(end)
    return sorted(ends)


def _last_quarters(
    points: list[tuple[int, date, Decimal]], count: int
) -> list[tuple[int, date, Decimal]]:
    picked: list[tuple[int, date, Decimal]] = []
    seen: set[date] = set()
    for item in points:
        end = item[1]
        if end in seen:
            continue
        if picked and (picked[-1][1] - end).days < 50:
            continue
        seen.add(end)
        picked.append(item)
        if len(picked) == count:
            break
    return picked


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


def _sum_instant(
    facts: dict[str, Any], concepts: tuple[tuple[str, str], ...], as_of: date
) -> Decimal | None:
    total = Decimal("0")
    found = False
    for taxonomy, concept in concepts:
        value = _latest_instant(facts, ((taxonomy, concept),), as_of)
        if value is None:
            continue
        total += value
        found = True
    return total if found else None


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
