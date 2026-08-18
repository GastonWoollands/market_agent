from __future__ import annotations

from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

from ingest.news_rss.errors import NewsParseError
from store.canonical import NewsHeadline


def headlines_from_rss(
    xml: str,
    *,
    category: str,
    query: str,
) -> list[NewsHeadline]:
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError as exc:
        raise NewsParseError(f"{category}: RSS is not XML") from exc
    items = list(root.findall("./channel/item"))
    if not items:
        items = list(root.findall(".//{*}item"))
    out: list[NewsHeadline] = []
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
        out.append(
            NewsHeadline(
                guid=guid[:512],
                title=title,
                url=link,
                publisher=_publisher(item, title),
                published_at=published,
                category=category,
                query=query,
            )
        )
    if not out:
        raise NewsParseError(f"{category}: no usable items")
    return out


def _text(item: ElementTree.Element, tag: str) -> str:
    node = item.find(tag)
    if node is None:
        node = item.find(f".//{{*}}{tag}")
    if node is None or node.text is None:
        return ""
    return node.text.strip()


def _publisher(item: ElementTree.Element, title: str) -> str:
    source = _text(item, "source")
    if source:
        return source[:255]
    if " - " in title:
        return title.rsplit(" - ", 1)[-1][:255]
    return "Google News"


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
