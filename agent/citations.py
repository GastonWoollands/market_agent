from __future__ import annotations

import json
import re
from typing import Any

TICKER_RE = re.compile(r"(?<![A-Z])\^?[A-Z]{2,5}\b")
PERCENT_RE = re.compile(r"(?<![A-Za-z0-9])([+-]?\d+(?:\.\d+)?)%")
STOP = frozenset(
    {
        "AI",
        "AM",
        "API",
        "ARE",
        "BLS",
        "BUT",
        "BOE",
        "BOJ",
        "CPI",
        "ECB",
        "ETF",
        "ETFS",
        "ET",
        "EV",
        "EBIT",
        "FCF",
        "FOMC",
        "FOR",
        "FROM",
        "GDP",
        "HAS",
        "HAVE",
        "HY",
        "IG",
        "JSON",
        "JOLTS",
        "MOM",
        "NFP",
        "NOT",
        "OAS",
        "PCE",
        "PM",
        "RRG",
        "RSS",
        "SEP",
        "SPX",
        "THAT",
        "THE",
        "THIS",
        "TTM",
        "US",
        "USA",
        "USD",
        "UTC",
        "WAS",
        "WEEK",
        "WILL",
        "WITH",
        "WTI",
        "YOY",
    }
)


def citation_issues(pack: dict[str, Any], text: str) -> list[str]:
    haystack = json.dumps(pack, default=str)
    numbers = _numbers(pack)
    issues: list[str] = []
    for ticker in TICKER_RE.findall(text):
        if ticker in STOP:
            continue
        if ticker not in haystack:
            issues.append(f"ticker:{ticker}")
    for match in PERCENT_RE.finditer(text):
        value = float(match.group(1))
        if not _cited_number(value, numbers):
            issues.append(f"pct:{match.group(0)}")
    return issues


def coverage_issues(pack: dict[str, Any], text: str) -> list[str]:
    issues: list[str] = []
    blob = text.lower()
    for row in pack.get("macro") or []:
        if not isinstance(row, dict):
            continue
        if row.get("series_id") == "CPIAUCSL" and row.get("yoy_pct") is not None:
            yoy = row["yoy_pct"]
            if "cpiaucsl" not in blob and "cpi" not in blob:
                issues.append("coverage:CPIAUCSL")
            if str(yoy) not in text:
                issues.append("coverage:CPIAUCSL_yoy")
        if row.get("series_id") == "ICSA" and row.get("change_label") == "weekly":
            mentions = "icsa" in blob or "claims" in blob
            if mentions and "weekly" not in blob:
                issues.append("coverage:ICSA_weekly")
    return issues


def _numbers(value: Any) -> list[float]:
    out: list[float] = []
    if isinstance(value, bool):
        return out
    if isinstance(value, int | float):
        out.append(float(value))
    elif isinstance(value, str):
        try:
            out.append(float(value))
        except ValueError:
            pass
    elif isinstance(value, dict):
        for item in value.values():
            out.extend(_numbers(item))
    elif isinstance(value, list):
        for item in value:
            out.extend(_numbers(item))
    return out


def _cited_number(value: float, allowed: list[float]) -> bool:
    if any(_number_matches(value, item) for item in allowed):
        return True
    # 0-1 pack values written as percents (implied_yes 0.8525 -> 85.25%).
    return any(_number_matches(value / 100.0, item) for item in allowed)


def _number_matches(value: float, item: float) -> bool:
    if abs(item - value) < 1e-9:
        return True
    if round(item, 1) == round(value, 1):
        return True
    if round(item, 2) == round(value, 2):
        return True
    return round(item, 4) == round(value, 4)
