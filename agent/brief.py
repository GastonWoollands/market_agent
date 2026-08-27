from pydantic import BaseModel, Field


class OutlookBrief(BaseModel):
    headline: str = Field(min_length=1)
    abstract: str = Field(min_length=1)
    conclusions: list[str] = Field(min_length=1, max_length=5)
    expect: str = Field(min_length=1)
    macro_md: str = Field(min_length=1)
    market_md: str = Field(min_length=1)
    near_term_md: str = Field(min_length=1)
