from __future__ import annotations

from collections import deque
from collections.abc import Sequence
from datetime import UTC, date, datetime
from typing import Any, Protocol

from ingest.polymarket.errors import PolymarketHttpError, PolymarketParseError
from store.canonical import OddsPoint
from store.catalog import PolymarketEvent

PICK_SOONEST = "soonest_end"
PICK_SECOND = "second_soonest_end"
PICK_FIRST = "first_open"
PENDING_SLUG_PREFIX = "__pending__"
_MONTHS = (
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
)


class OddsOccupancyError(ValueError):
    """Two catalog slots cannot persist the same Gamma slug."""


class OddsSlugCycle(OddsOccupancyError):
    """Slots swap slugs; the writer must park before the final upsert."""


class GammaEvents(Protocol):
    def fetch_event(self, slug: str) -> OddsPoint: ...

    def search_events(self, query: str) -> list[dict[str, Any]]: ...


def pending_odds_slug(slot: str) -> str:
    return f"{PENDING_SLUG_PREFIX}{slot}"


def is_rotatable(exc: BaseException) -> bool:
    if isinstance(exc, PolymarketHttpError) and exc.status_code == 404:
        return True
    if isinstance(exc, PolymarketParseError):
        text = str(exc).lower()
        return "closed" in text or "no open markets" in text
    return False


def event_is_open(payload: dict[str, Any]) -> bool:
    if payload.get("closed") is True:
        return False
    if payload.get("active") is False:
        return False
    return True


def ranked_open_slugs(
    hits: Sequence[dict[str, Any]],
    *,
    slug_prefix: str,
    pick: str = PICK_SOONEST,
) -> list[str]:
    if not slug_prefix:
        return []
    matched = [
        event
        for event in hits
        if isinstance(event, dict) and _matches_prefix(event, slug_prefix)
    ]
    if pick == PICK_FIRST:
        ordered = matched
    else:
        ordered = sorted(matched, key=_end_sort_key)
        if pick == PICK_SECOND:
            ordered = ordered[1:]
    slugs: list[str] = []
    for event in ordered:
        slug = event.get("slug")
        if isinstance(slug, str) and slug not in slugs:
            slugs.append(slug)
    return slugs


def month_successors(seed: str | None, prefix: str | None, *, count: int = 4) -> list[str]:
    """Next prefix+month-year slugs after a dated seed (optional numeric suffix)."""
    if not seed or not prefix or not seed.startswith(prefix):
        return []
    bits = seed[len(prefix) :].split("-")
    if len(bits) < 2:
        return []
    month, year_s = bits[0].lower(), bits[1]
    if month not in _MONTHS or not (year_s.isdigit() and len(year_s) == 4):
        return []
    year = int(year_s)
    idx = _MONTHS.index(month)
    suffix = "-".join(bits[2:])
    out: list[str] = []
    for step in range(1, count + 1):
        shifted = idx + step
        next_year = year + shifted // 12
        next_month = _MONTHS[shifted % 12]
        base = f"{prefix}{next_month}-{next_year}"
        out.append(base)
        if suffix:
            out.append(f"{base}-{suffix}")
    return out


def calendar_month_slugs(
    prefix: str | None,
    *,
    today: date,
    back: int = 1,
    ahead: int = 3,
) -> list[str]:
    if not prefix or not prefix.endswith("-"):
        return []
    out: list[str] = []
    for delta in range(-back, ahead + 1):
        month_index = today.month - 1 + delta
        year = today.year + month_index // 12
        month_index = month_index % 12
        out.append(f"{prefix}{_MONTHS[month_index]}-{year}")
    return out


def load_slot(
    client: GammaEvents,
    item: PolymarketEvent,
    *,
    current_slug: str | None = None,
    search_hints: dict[str, list[str]] | None = None,
    today: date | None = None,
) -> OddsPoint:
    tried: list[str] = []
    last_exc: BaseException | None = None
    day = today or datetime.now(UTC).date()

    def attempt(slug: str) -> OddsPoint | None:
        nonlocal last_exc
        if slug in tried:
            return None
        tried.append(slug)
        try:
            point = client.fetch_event(slug)
        except PolymarketHttpError as exc:
            if exc.status_code == 429:
                raise
            if not is_rotatable(exc):
                raise
            last_exc = exc
            return None
        except (PolymarketParseError, ValueError) as exc:
            if not is_rotatable(exc):
                raise
            last_exc = exc
            return None
        return point.model_copy(update={"slot": item.slot})

    # second_soonest must rank the open set. Returning an open current_slug would
    # pin next_fomc on the front meeting after the prior contract expires.
    if item.pick != PICK_SECOND:
        guesses = _try_slugs(current_slug, item.slug)
        for slug in month_successors(current_slug or item.slug, item.slug_prefix):
            if slug not in guesses:
                guesses.append(slug)
        for slug in calendar_month_slugs(item.slug_prefix, today=day):
            if slug not in guesses:
                guesses.append(slug)
        for slug in guesses:
            point = attempt(slug)
            if point is not None:
                return point

    hits: list[dict[str, Any]] = []
    seen_hits: set[str] = set()
    if item.slug_prefix:
        for query in _search_queries(item, search_hints):
            for event in client.search_events(query):
                slug = event.get("slug") if isinstance(event, dict) else None
                if not isinstance(slug, str) or slug in seen_hits:
                    continue
                seen_hits.add(slug)
                hits.append(event)
        for slug in ranked_open_slugs(hits, slug_prefix=item.slug_prefix, pick=item.pick):
            point = attempt(slug)
            if point is not None:
                return point

    found = [event.get("slug") for event in hits if isinstance(event, dict)]
    extra = f"; search candidates: {found[:8]}" if found else ""
    prefix = item.slug_prefix or "prefix"
    raise PolymarketParseError(
        f"{item.slot}: no open market matching {prefix}{extra}"
    ) from last_exc


def order_odds_upserts(
    points: Sequence[OddsPoint],
    current_by_slot: dict[str, str],
) -> list[OddsPoint]:
    """Write leavers before takers so uq_odds_snapshot_slug stays satisfied."""
    if not points:
        return []
    by_slot: dict[str, OddsPoint] = {}
    for point in points:
        if point.slot in by_slot:
            raise OddsOccupancyError(f"duplicate slot in odds batch: {point.slot}")
        by_slot[point.slot] = point

    seen_slug: dict[str, str] = {}
    for point in points:
        other = seen_slug.get(point.slug)
        if other is not None:
            raise OddsOccupancyError(
                f"{other} and {point.slot} resolved to the same slug ({point.slug})"
            )
        seen_slug[point.slug] = point.slot

    owners = {slug: slot for slot, slug in current_by_slot.items() if slug}
    write_slots = set(by_slot)
    for point in points:
        owner = owners.get(point.slug)
        if owner is None or owner == point.slot:
            continue
        if owner not in write_slots:
            raise OddsOccupancyError(
                f"{point.slot} cannot take slug {point.slug}; still held by {owner}"
            )

    dependents: dict[str, list[str]] = {slot: [] for slot in by_slot}
    indegree: dict[str, int] = {slot: 0 for slot in by_slot}
    for point in points:
        owner = owners.get(point.slug)
        if owner is None or owner == point.slot or owner not in write_slots:
            continue
        dependents[owner].append(point.slot)
        indegree[point.slot] += 1

    index = {point.slot: i for i, point in enumerate(points)}
    ready = deque(
        sorted(
            (slot for slot, degree in indegree.items() if degree == 0),
            key=lambda slot: index[slot],
        )
    )
    ordered: list[OddsPoint] = []
    while ready:
        slot = ready.popleft()
        ordered.append(by_slot[slot])
        for dep in sorted(dependents[slot], key=lambda item: index[item]):
            indegree[dep] -= 1
            if indegree[dep] == 0:
                ready.append(dep)
    if len(ordered) != len(points):
        stuck = [slot for slot, degree in indegree.items() if degree > 0]
        raise OddsSlugCycle(f"odds slug cycle among {stuck}")
    return ordered


def drop_occupied(
    points: Sequence[OddsPoint],
    current_by_slot: dict[str, str],
) -> tuple[list[OddsPoint], list[str]]:
    """Drop points that cannot be written so one stuck slot does not block the rest."""
    kept = list(points)
    dropped: list[str] = []
    while True:
        seen: set[str] = set()
        clash: OddsPoint | None = None
        reason = ""
        for point in kept:
            if point.slug in seen:
                clash, reason = point, f"slug {point.slug} already taken in this batch"
                break
            seen.add(point.slug)
        if clash is None:
            write_slots = {point.slot for point in kept}
            owners = {slug: slot for slot, slug in current_by_slot.items() if slug}
            for point in kept:
                owner = owners.get(point.slug)
                if owner is not None and owner != point.slot and owner not in write_slots:
                    clash, reason = point, f"slug {point.slug} still held by {owner}"
                    break
        if clash is None:
            return kept, dropped
        kept = [point for point in kept if point is not clash]
        dropped.append(f"{clash.slot}: {reason}")


def plan_odds_upserts(
    points: Sequence[OddsPoint],
    current_by_slot: dict[str, str],
) -> tuple[list[OddsPoint], bool]:
    """Return (write order, park-first). Park only when slots swap slugs."""
    try:
        return order_odds_upserts(points, current_by_slot), False
    except OddsSlugCycle:
        return list(points), True


def _matches_prefix(event: dict[str, Any], slug_prefix: str) -> bool:
    slug = event.get("slug")
    if not isinstance(slug, str) or not slug.startswith(slug_prefix):
        return False
    return event_is_open(event)


def _parse_end(event: dict[str, Any]) -> datetime | None:
    raw = event.get("endDate") or event.get("end_date")
    if not isinstance(raw, str) or not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _end_sort_key(event: dict[str, Any]) -> tuple[int, datetime, str]:
    end = _parse_end(event)
    slug = str(event.get("slug") or "")
    if end is None:
        return (1, datetime.max.replace(tzinfo=UTC), slug)
    return (0, end, slug)


def _try_slugs(current_slug: str | None, seed: str | None) -> list[str]:
    out: list[str] = []
    for slug in (current_slug, seed):
        if slug and slug not in out:
            out.append(slug)
    return out


def _search_queries(
    item: PolymarketEvent,
    search_hints: dict[str, list[str]] | None,
) -> list[str]:
    out: list[str] = []
    if item.query:
        out.append(item.query)
    for query in (search_hints or {}).get(item.category) or []:
        if query not in out:
            out.append(query)
    return out
