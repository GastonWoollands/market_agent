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
        "BEA",
        "BLS",
        "BUT",
        "BOE",
        "BOJ",
        "CPI",
        "DR",
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
        "ISM",
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
        "TL",
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
    """Check that all tickers, percents, and yields in the text appear in the pack."""
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
    """Check that required series are mentioned when present in the pack."""
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


def validate_brief_fields(brief_json: dict[str, Any]) -> list[str]:
    """Validate that new narrative fields meet minimum quality standards."""
    issues: list[str] = []
    
    # Check tldr is not generic
    tldr = brief_json.get("tldr", "").lower()
    if any(phrase in tldr for phrase in ["mixed", "uncertain", "waiting", "unclear"]):
        if len(tldr) < 100:  # Allow these words in longer, detailed tldr
            issues.append("tldr:too_generic")
    
    # Check what_happened explains mechanism
    what_happened = brief_json.get("what_happened", "")
    if what_happened and len(what_happened) < 100:
        issues.append("what_happened:too_short")
    if "template fallback" not in what_happened.lower():
        # Only check if not template
        sequence_words = ["led", "followed", "first", "then", "after"]
        if not any(word in what_happened.lower() for word in sequence_words):
            issues.append("what_happened:no_sequence")
    
    # Check current_positioning has specific levels
    positioning = brief_json.get("current_positioning", "")
    if positioning and "unavailable" not in positioning.lower():
        # Should mention at least one spread or level
        level_terms = [
            "2s10s",
            "10y",
            "fed_vs_2y",
            "breakeven",
            "hyg",
            "lqd",
            "dxy",
        ]
        has_level = any(term in positioning.lower() for term in level_terms)
        if not has_level:
            issues.append("positioning:no_levels")
    
    # Check drivers distinguishes events from forces
    drivers = brief_json.get("drivers", "")
    if drivers and len(drivers) < 80:
        issues.append("drivers:too_short")
    
    # Check watch_today has scenarios
    watch = brief_json.get("watch_today", [])
    if isinstance(watch, list) and watch:
        for scenario in watch:
            if isinstance(scenario, dict):
                if not scenario.get("outcome_bullish") or not scenario.get("outcome_bearish"):
                    issues.append("watch_today:missing_outcomes")
                    break
                if "template" not in scenario.get("outcome_bullish", "").lower():
                    # Check for specific market impacts (expanded for market-agnostic coverage)
                    bullish = scenario.get("outcome_bullish", "").lower()
                    market_terms = [
                        "2y", "10y", "30y", "yields", "yield", "curve",
                        "equities", "equity", "stocks", "rallies", "rally",
                        "bp", "basis", "odds", "probability",
                        "hy", "ig", "credit", "spreads", "spread",
                        "vix", "vol", "volatility",
                        "dollar", "dxy", "yen", "euro",
                        "gold", "oil", "commodities",
                        "recover", "stabilize", "drop", "fall", "rise"
                    ]
                    if not any(market in bullish for market in market_terms):
                        issues.append("watch_today:generic_outcome")
                        break
    
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
