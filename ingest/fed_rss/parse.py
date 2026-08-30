from __future__ import annotations

import re
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from html import unescape
from xml.etree import ElementTree

from ingest.fed_rss.errors import FedRssParseError
from store.canonical import PolicyDoc

EXCERPT_MAX = 500
TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")
SPEAKER_RE = re.compile(
    r"\b(?:[Bb]y|[Rr]emarks by|[Ss]peech by|[Tt]estimony by|[Ss]tatement by)\s+"
    r"((?:Chairman|Chair|Vice Chair(?: for Supervision)?|Governor)\s+[A-Z][A-Za-z.\-]+"
    r"(?:\s+[A-Z][A-Za-z.\-]+)?)"
)
LEADING_SPEAKER_RE = re.compile(
    r"^((?:Chairman|Chair|Vice Chair(?: for Supervision)?|Governor)\s+[A-Z][A-Za-z.\-]+"
    r"(?:\s+[A-Z][A-Za-z.\-]+)?)"
)
FEED_KIND = {
    "speeches": "speech",
    "testimony": "testimony",
    "press_monetary": "statement",
}
COMMA_SPEAKER_RE = re.compile(r"^([A-Z][A-Za-z\-]+),\s+\S")
VENUE_RE = re.compile(
    r"^(?:Speech|Remarks|Testimony|Statement)\s+At\b",
    re.IGNORECASE,
)


def docs_from_rss(xml: str, *, feed: str) -> list[PolicyDoc]:
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError as exc:
        raise FedRssParseError(f"{feed}: RSS is not XML") from exc
    items = list(root.findall("./channel/item"))
    if not items:
        items = list(root.findall(".//{*}item"))
    out: list[PolicyDoc] = []
    seen: set[str] = set()
    for item in items:
        title = _text(item, "title")
        link = _text(item, "link")
        guid = _text(item, "guid") or link
        if not title or not link or not guid or guid in seen:
            continue
        published = _published(item)
        if published is None:
            continue
        seen.add(guid)
        description = _text(item, "description")
        excerpt = _excerpt(description)
        out.append(
            PolicyDoc(
                guid=guid[:512],
                published_at=published,
                title=title,
                url=link,
                kind=_kind(feed, title),
                speaker=_speaker(title, description),
                excerpt=excerpt,
            )
        )
    if not out:
        raise FedRssParseError(f"{feed}: no usable items")
    return out


def _kind(feed: str, title: str) -> str:
    if "minutes" in title.lower():
        return "minutes"
    return FEED_KIND.get(feed, "statement")


def _speaker(title: str, description: str) -> str | None:
    for blob in (title, description):
        match = SPEAKER_RE.search(blob) or LEADING_SPEAKER_RE.search(blob.strip())
        if match:
            return match.group(1).strip()[:128]
    comma = COMMA_SPEAKER_RE.match(title.strip())
    if comma:
        return comma.group(1)[:128]
    return None


def is_venue_excerpt(text: str | None) -> bool:
    if not text or not text.strip():
        return True
    return VENUE_RE.match(text.strip()) is not None


def display_title(title: str, speaker: str | None = None) -> str:
    text = title.strip()
    comma = re.match(r"^([A-Z][A-Za-z\-]+),\s+(.+)$", text)
    if comma:
        name, talk = comma.group(1), comma.group(2).strip()
        return f"{name}: {talk}"
    if speaker and speaker not in text:
        return f"{speaker}: {text}"
    return text


def _excerpt(raw: str) -> str | None:
    if not raw.strip():
        return None
    text = unescape(TAG_RE.sub(" ", raw))
    text = WS_RE.sub(" ", text).strip()
    if not text:
        return None
    return text[:EXCERPT_MAX]


def _text(item: ElementTree.Element, tag: str) -> str:
    node = item.find(tag)
    if node is None:
        node = item.find(f".//{{*}}{tag}")
    if node is None or node.text is None:
        return ""
    return node.text.strip()


def _published(item: ElementTree.Element) -> datetime | None:
    raw = _text(item, "pubDate") or _text(item, "published")
    if not raw:
        return None
    try:
        parsed = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
