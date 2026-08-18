from datetime import date

from pydantic import BaseModel, ConfigDict, Field
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


class ValuationConfig(BaseModel):
    description: str | None = None
    min_revenue_usd: int = 1_000_000_000
    exchanges: list[str] = Field(default_factory=lambda: ["NYSE", "Nasdaq", "NYSE American"])
    rebuild: str = "monthly"


class UniversesFile(BaseModel):
    model_config = ConfigDict(extra="ignore")

    tape: UniverseCatalog
    watchlist: UniverseCatalog
    live: LiveTapeConfig = Field(default_factory=LiveTapeConfig)
    valuation: ValuationConfig = Field(default_factory=ValuationConfig)


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


class FredSeriesFile(BaseModel):
    series: list[FredSeriesItem] = Field(default_factory=list)


def load_fred_series() -> FredSeriesFile:
    path = CONFIG_DIR / "fred_series.yaml"
    with path.open(encoding="utf-8") as handle:
        raw = safe_load(handle)
    return FredSeriesFile.model_validate(raw)


class PolymarketEvent(BaseModel):
    slug: str
    label: str
    category: str
    show_on_live: bool = True
    notes: str | None = None


class PolymarketFile(BaseModel):
    events: list[PolymarketEvent] = Field(default_factory=list)
    search_hints: dict[str, list[str]] = Field(default_factory=dict)


def load_polymarket() -> PolymarketFile:
    path = CONFIG_DIR / "polymarket_slugs.yaml"
    with path.open(encoding="utf-8") as handle:
        raw = safe_load(handle)
    return PolymarketFile.model_validate(raw)


class NewsBucket(BaseModel):
    category: str
    queries: list[str] = Field(default_factory=list)


class NewsQueriesFile(BaseModel):
    buckets: list[NewsBucket] = Field(default_factory=list)


def load_news_queries() -> NewsQueriesFile:
    path = CONFIG_DIR / "news_queries.yaml"
    with path.open(encoding="utf-8") as handle:
        raw = safe_load(handle)
    return NewsQueriesFile.model_validate(raw)


class CatalystItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    date: date
    title: str
    sep: bool = False
    type: str | None = None


class CatalystsFile(BaseModel):
    timezone: str = "America/New_York"
    fomc: list[CatalystItem] = Field(default_factory=list)
    cpi: list[CatalystItem] = Field(default_factory=list)
    other: list[CatalystItem] = Field(default_factory=list)


def load_catalysts() -> CatalystsFile:
    path = CONFIG_DIR / "catalysts.yaml"
    with path.open(encoding="utf-8") as handle:
        raw = safe_load(handle)
    return CatalystsFile.model_validate(raw)
