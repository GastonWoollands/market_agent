from pydantic import BaseModel, Field


class WatchScenario(BaseModel):
    """Structured scenario for a watch item with branching outcomes."""
    catalyst: str = Field(min_length=1)
    date: str | None = None
    time: str | None = None
    outcome_bullish: str = Field(min_length=1)
    outcome_bearish: str = Field(min_length=1)
    threshold: str | None = None


class CalendarItem(BaseModel):
    """Structured calendar entry with consensus/prior."""
    date: str = Field(min_length=1)
    time: str | None = None
    event: str = Field(min_length=1)
    consensus: str | None = None
    prior: str | None = None
    source: str | None = None


class OutlookBrief(BaseModel):
    headline: str = Field(min_length=1)
    
    # New core sections
    tldr: str = Field(min_length=1, description="1-2 sentence synthesis")
    what_happened: str = Field(min_length=1, description="Yesterday's cross-asset mechanism")
    current_positioning: str = Field(min_length=1, description="Key levels and spreads now")
    drivers: str = Field(min_length=1, description="What's moving markets")
    
    # Scenario planning
    watch_today: list[WatchScenario] = Field(default_factory=list, max_length=5)
    invalidation: str = Field(min_length=1, description="Explicit triggers that break the read")
    
    # Deep sections (renamed for clarity)
    macro_deep: str = Field(min_length=1, description="Curve, inflation, employment, fiscal")
    market_deep: str = Field(min_length=1, description="Risk-On, credit, odds, positioning")
    policy_deep: str = Field(min_length=1, description="Fed/ECB/BOJ stance and next tests")
    geopolitical_deep: str | None = Field(default=None, description="Energy, trade, conflicts (optional)")
    
    # Calendar
    calendar: list[CalendarItem] = Field(default_factory=list)
    
    # Legacy fields (keep for backward compat during migration)
    abstract: str = Field(min_length=1)
    conclusions: list[str] = Field(min_length=1, max_length=5)
    expect: str = Field(min_length=1)
    live_md: str = Field(min_length=1)
    macro_md: str = Field(default="", description="Legacy: use macro_deep")
    market_md: str = Field(default="", description="Legacy: use market_deep")
    near_term_md: str = Field(default="", description="Legacy: use expect + calendar")
