from pydantic import BaseModel, Field


class OutlookBrief(BaseModel):
    headline: str = Field(min_length=1)
    body_md: str = Field(min_length=1)
