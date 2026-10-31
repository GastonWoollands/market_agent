"""SIC code → tape sector name (approximate GICS). Map lives in config/sic_sectors.yaml."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field
from yaml import safe_load

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "sic_sectors.yaml"
SECTORS = frozenset(
    {
        "Information Technology",
        "Financials",
        "Health Care",
        "Consumer Discretionary",
        "Consumer Staples",
        "Industrials",
        "Energy",
        "Materials",
        "Utilities",
        "Real Estate",
        "Communication Services",
    }
)


class SicRange(BaseModel):
    lo: int = Field(alias="from")
    hi: int = Field(alias="to")
    sector: str


class SicMap(BaseModel):
    tickers: dict[str, str] = Field(default_factory=dict)
    ranges: list[SicRange] = Field(default_factory=list)

    def sector_for(self, sic: int | None, ticker: str | None = None) -> str | None:
        if ticker and ticker.upper() in self.tickers:
            return self.tickers[ticker.upper()]
        if sic is None:
            return None
        for item in self.ranges:
            if item.lo <= sic <= item.hi:
                return item.sector
        return None


@lru_cache(maxsize=1)
def load_sic_map(path: Path = CONFIG_PATH) -> SicMap:
    with path.open(encoding="utf-8") as handle:
        sic_map = SicMap.model_validate(safe_load(handle))
    unknown = {item.sector for item in sic_map.ranges} | set(sic_map.tickers.values())
    unknown -= SECTORS
    if unknown:
        raise ValueError(f"sic_sectors.yaml names unknown sectors: {sorted(unknown)}")
    return sic_map
