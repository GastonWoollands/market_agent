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


class UniverseCatalog(BaseModel):
    description: str | None = None
    instruments: list[CatalogInstrument] = Field(default_factory=list)


class LiveHeaderItem(BaseModel):
    ticker: str
    label: str | None = None


class LiveTapeConfig(BaseModel):
    header: list[LiveHeaderItem] = Field(default_factory=list)
    mover_roles: list[str] = Field(default_factory=lambda: ["sector", "group"])


class UniversesFile(BaseModel):
    model_config = ConfigDict(extra="ignore")

    tape: UniverseCatalog
    watchlist: UniverseCatalog
    live: LiveTapeConfig = Field(default_factory=LiveTapeConfig)


def load_universes() -> UniversesFile:
    path = CONFIG_DIR / "universes.yaml"
    with path.open(encoding="utf-8") as handle:
        raw = safe_load(handle)
    return UniversesFile.model_validate(raw)


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
