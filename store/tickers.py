from __future__ import annotations

import re

US_TICKER = re.compile(r"^\^?[A-Z]{1,5}(-[A-Z]{1,2})?$")

TV_INDEX = {
    "^GSPC": "SPX",
    "^IXIC": "IXIC",
    "^DJI": "DJI",
    "^RUT": "RUT",
    "^VIX": "VIX",
}


class TickerError(ValueError):
    pass


def normalize_us_ticker(raw: str) -> str:
    ticker = raw.strip().upper()
    if not ticker:
        raise TickerError("ticker is required")
    if "." in ticker:
        raise TickerError("US listings only (no .L / .T)")
    if not US_TICKER.match(ticker):
        raise TickerError("invalid ticker")
    return ticker


def tv_symbol(ticker: str) -> str:
    key = ticker.strip().upper()
    return TV_INDEX.get(key, key.lstrip("^"))
