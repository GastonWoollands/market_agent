"""Headline selection shared by the evidence pack and GET /outlook.

One rule set, applied at read time to stored `news_item` rows from every source:
drop blocked publishers and junk titles, drop repeated stories, rank by publisher tier
then recency, cap per bucket. Rules live in `config/news_sources.yaml`.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from store.catalog import NewsSourcesFile, publisher_key

PER_BUCKET = 3
BUCKET_CAPS = {"wire": 6}
SAME_STORY = 0.8
_WORD = re.compile(r"[a-z0-9]+")
_STOP = frozenset(
    {"the", "and", "for", "with", "after", "amid", "from", "into", "over", "says", "said", "its"}
)


class NewsRow(Protocol):
    title: str
    publisher: str
    published_at: datetime
    category: str
    query: str


@dataclass(frozen=True)
class NewsRules:
    tier_of: dict[str, int]
    blocked: frozenset[str]
    patterns: tuple[re.Pattern[str], ...]

    @classmethod
    def from_catalog(cls, catalog: NewsSourcesFile) -> NewsRules:
        return cls(
            tier_of=catalog.tier_of(),
            blocked=catalog.blocked_keys(),
            patterns=tuple(catalog.title_patterns()),
        )

    @property
    def unknown_tier(self) -> int:
        return max(self.tier_of.values(), default=0) + 1


def bare_title(title: str, publisher: str) -> str:
    """Google titles end with " - Publisher"; drop it so rules see the headline only."""
    head, sep, tail = title.rpartition(" - ")
    if sep and publisher_key(tail) == publisher_key(publisher):
        return head.strip()
    return title.strip()


def is_junk(row: NewsRow, rules: NewsRules) -> bool:
    if publisher_key(row.publisher) in rules.blocked:
        return True
    title = bare_title(row.title, row.publisher)
    return any(pattern.search(title) for pattern in rules.patterns)


def tier(row: NewsRow, rules: NewsRules) -> int:
    return rules.tier_of.get(publisher_key(row.publisher), rules.unknown_tier)


def bucket_key(row: NewsRow) -> tuple[str, str]:
    """Company news is bucketed per ticker so one name cannot take every slot."""
    return (row.category, row.query if row.category == "company" else "")


def story_words(row: NewsRow) -> frozenset[str]:
    words = _WORD.findall(bare_title(row.title, row.publisher).lower())
    return frozenset(word for word in words if len(word) > 2 and word not in _STOP)


def same_story(left: frozenset[str], right: frozenset[str]) -> bool:
    if not left or not right:
        return False
    return len(left & right) / len(left | right) >= SAME_STORY


def select_news[Row: NewsRow](
    rows: Sequence[Row],
    rules: NewsRules,
    *,
    per_bucket: int = PER_BUCKET,
    bucket_caps: dict[str, int] | None = None,
) -> list[Row]:
    """Best rows per bucket, ordered tier first, then newest. Input order does not matter."""
    caps = BUCKET_CAPS if bucket_caps is None else bucket_caps
    ranked = sorted(
        (row for row in rows if not is_junk(row, rules)),
        key=lambda row: (tier(row, rules), -row.published_at.timestamp()),
    )
    kept: list[Row] = []
    stories: list[frozenset[str]] = []
    counts: dict[tuple[str, str], int] = {}
    for row in ranked:
        key = bucket_key(row)
        if counts.get(key, 0) >= caps.get(row.category, per_bucket):
            continue
        words = story_words(row)
        if any(same_story(words, seen) for seen in stories):
            continue
        kept.append(row)
        stories.append(words)
        counts[key] = counts.get(key, 0) + 1
    return kept
