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
        "CPI",
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
        "JSON",
        "MOM",
        "NOT",
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
    for item in allowed:
        if abs(item - value) < 1e-9:
            return True
        if round(item, 1) == round(value, 1):
            return True
        if round(item, 2) == round(value, 2):
            return True
        if round(item, 4) == round(value, 4):
            return True
    return False
