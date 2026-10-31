import re
from datetime import date
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator
from yaml import safe_load

from store.settings import CONFIG_DIR


class CatalogInstrument(BaseModel):
    ticker: str
    yahoo: str
    name: str
    asset_class: str = "equity"
    role: str | None = None
    sector: str | None = None
    industry: str | None = None
    exchange: str | None = None
    cik: str | None = None


class UniverseCatalog(BaseModel):
    description: str | None = None
    instruments: list[CatalogInstrument] = Field(default_factory=list)


class LiveHeaderItem(BaseModel):
    ticker: str
    label: str | None = None


class LiveTapeConfig(BaseModel):
    header: list[LiveHeaderItem] = Field(default_factory=list)
    mover_roles: list[str] = Field(default_factory=lambda: ["sector", "group"])
    intl_section: list[LiveHeaderItem] = Field(default_factory=list)
    yields_section: list[LiveHeaderItem] = Field(default_factory=list)


class ValuationConfig(BaseModel):
    description: str | None = None
    min_revenue_usd: int = 1_000_000_000
    exchanges: list[str] = Field(default_factory=lambda: ["NYSE", "Nasdaq", "NYSE American"])
    rebuild: str = "monthly"


class GemsConfig(BaseModel):
    description: str | None = None
    min_market_cap_usd: int = 300_000_000
    max_market_cap_usd: int = 2_000_000_000
    min_revenue_usd: int = 50_000_000
    min_revenue_growth_yoy: float = 0.15
    min_fcf_yield: float = 0.04
    max_debt_to_equity: float = 0.5


class UniversesFile(BaseModel):
    model_config = ConfigDict(extra="ignore")

    tape: UniverseCatalog
    watchlist: UniverseCatalog
    live: LiveTapeConfig = Field(default_factory=LiveTapeConfig)
    valuation: ValuationConfig = Field(default_factory=ValuationConfig)
    gems: GemsConfig = Field(default_factory=GemsConfig)


def load_universes() -> UniversesFile:
    path = CONFIG_DIR / "universes.yaml"
    with path.open(encoding="utf-8") as handle:
        raw = safe_load(handle)
    return UniversesFile.model_validate(raw)


def tape_with_roles(catalog: UniversesFile, roles: list[str]) -> list[CatalogInstrument]:
    wanted = set(roles)
    return [item for item in catalog.tape.instruments if item.role in wanted]


class FredSeriesItem(BaseModel):
    id: str
    name: str
    unit: str
    category: str | None = None
    insight: str | None = None
    watch: list[str] = Field(default_factory=list)
    frequency: str = "daily"
    region: str = "us"
    pack_view: str = "level"
    show_on_live: bool = True
    # False keeps reference-only series (rating curve buckets) out of the writer pack.
    in_pack: bool = True
    spine: bool = False
    scale: float = 1.0


class FredSeriesFile(BaseModel):
    series: list[FredSeriesItem] = Field(default_factory=list)


def load_fred_series() -> FredSeriesFile:
    path = CONFIG_DIR / "fred_series.yaml"
    with path.open(encoding="utf-8") as handle:
        raw = safe_load(handle)
    return FredSeriesFile.model_validate(raw)


PolymarketPick = Literal["soonest_end", "second_soonest_end", "first_open"]


class PolymarketEvent(BaseModel):
    slot: str
    label: str
    category: str
    show_on_live: bool = True
    notes: str | None = None
    short_label: str | None = None
    slug: str | None = None
    query: str | None = None
    slug_prefix: str | None = None
    pick: PolymarketPick = "soonest_end"


class PolymarketFile(BaseModel):
    events: list[PolymarketEvent] = Field(default_factory=list)
    search_hints: dict[str, list[str]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def unique_slots(self) -> Self:
        slots = [item.slot for item in self.events]
        if len(slots) != len(set(slots)):
            raise ValueError("duplicate Polymarket slot")
        return self


def load_polymarket() -> PolymarketFile:
    path = CONFIG_DIR / "polymarket_slugs.yaml"
    with path.open(encoding="utf-8") as handle:
        raw = safe_load(handle)
    return PolymarketFile.model_validate(raw)


class NewsBucket(BaseModel):
    category: str
    queries: list[str] = Field(default_factory=list)


class NewsQueriesFile(BaseModel):
    freshness_days: int = Field(default=2, ge=1, le=30)
    buckets: list[NewsBucket] = Field(default_factory=list)


def load_news_queries() -> NewsQueriesFile:
    path = CONFIG_DIR / "news_queries.yaml"
    with path.open(encoding="utf-8") as handle:
        raw = safe_load(handle)
    return NewsQueriesFile.model_validate(raw)


def publisher_key(name: str) -> str:
    """Normalized publisher identity shared by the catalog and stored rows."""
    text = name.strip().lower()
    text = text.removeprefix("www.").removesuffix(".com")
    return re.sub(r"[^a-z0-9]", "", text)


class NewsSourcesFile(BaseModel):
    """Read-time headline rules (`config/news_sources.yaml`)."""

    model_config = ConfigDict(frozen=True)

    tiers: dict[int, list[str]] = Field(default_factory=dict)
    blocked: list[str] = Field(default_factory=list)
    reject_title_patterns: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check(self) -> Self:
        seen: dict[str, str] = {}
        for label, names in [
            *((f"tier {k}", v) for k, v in self.tiers.items()),
            ("blocked", self.blocked),
        ]:
            for name in names:
                key = publisher_key(name)
                if not key:
                    raise ValueError(f"{label}: empty publisher name {name!r}")
                if key in seen and seen[key] != label:
                    raise ValueError(f"{name!r} listed in both {seen[key]} and {label}")
                seen[key] = label
        for pattern in self.reject_title_patterns:
            try:
                re.compile(pattern, re.IGNORECASE)
            except re.error as exc:
                raise ValueError(f"bad reject_title_patterns entry {pattern!r}: {exc}") from exc
        return self

    def tier_of(self) -> dict[str, int]:
        return {publisher_key(name): tier for tier, names in self.tiers.items() for name in names}

    def blocked_keys(self) -> frozenset[str]:
        return frozenset(publisher_key(name) for name in self.blocked)

    def title_patterns(self) -> list[re.Pattern[str]]:
        return [re.compile(pattern, re.IGNORECASE) for pattern in self.reject_title_patterns]


def load_news_sources() -> NewsSourcesFile:
    path = CONFIG_DIR / "news_sources.yaml"
    with path.open(encoding="utf-8") as handle:
        raw = safe_load(handle)
    return NewsSourcesFile.model_validate(raw or {})


class CatalystItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    date: date
    title: str
    sep: bool = False
    type: str | None = None
    time: str | None = None


class CatalystsFile(BaseModel):
    timezone: str = "America/New_York"
    default_times: dict[str, str] = Field(default_factory=dict)
    fomc: list[CatalystItem] = Field(default_factory=list)
    cpi: list[CatalystItem] = Field(default_factory=list)
    pce: list[CatalystItem] = Field(default_factory=list)
    nfp: list[CatalystItem] = Field(default_factory=list)
    gdp: list[CatalystItem] = Field(default_factory=list)
    jolts: list[CatalystItem] = Field(default_factory=list)
    speech: list[CatalystItem] = Field(default_factory=list)
    minutes: list[CatalystItem] = Field(default_factory=list)
    beige_book: list[CatalystItem] = Field(default_factory=list)
    ism: list[CatalystItem] = Field(default_factory=list)
    treasury: list[CatalystItem] = Field(default_factory=list)
    other: list[CatalystItem] = Field(default_factory=list)


def load_catalysts() -> CatalystsFile:
    path = CONFIG_DIR / "catalysts.yaml"
    with path.open(encoding="utf-8") as handle:
        raw = safe_load(handle)
    return CatalystsFile.model_validate(raw)


class CreditCalibrationName(BaseModel):
    ticker: str
    bucket: Literal["AAA", "AA", "A", "BBB", "BB", "B", "CCC"]
    rating: str
    agency: str
    as_of: str | None = None
    source: str | None = None
    confidence: Literal["high", "medium", "low"]
    fit: bool = True
    holdout: bool = False
    note: str | None = None

    @property
    def fitted(self) -> bool:
        return self.fit and not self.holdout and self.confidence != "low"


class CreditCalibrationFile(BaseModel):
    version: str
    exclude_sectors: list[str] = Field(default_factory=list)
    exclude_tickers: list[str] = Field(default_factory=list)
    names: list[CreditCalibrationName] = Field(default_factory=list)

    def by_ticker(self) -> dict[str, CreditCalibrationName]:
        return {item.ticker: item for item in self.names}


def load_credit_calibration() -> CreditCalibrationFile:
    path = CONFIG_DIR / "credit_calibration.yaml"
    with path.open(encoding="utf-8") as handle:
        raw = safe_load(handle)
    return CreditCalibrationFile.model_validate(raw)
