from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from agent.pack import EVENTS_AHEAD_DAYS, sources_from_counts, store_counts
from api.schemas import OutlookEvent, OutlookNews, OutlookResponse, OutlookSource
from store.models import EventItem, EvidencePack, NewsItem
from store.repos import latest_evidence_pack, latest_jobs, latest_news, upcoming_events

ET = ZoneInfo("America/New_York")
STALE_AFTER = timedelta(days=2)
NEWS_SINCE = timedelta(days=3)
NEWS_LIMIT = 40


def build_outlook(
    *,
    as_of: date,
    now: datetime,
    news: list[NewsItem],
    events: list[EventItem],
    sources: list[OutlookSource],
    pack: EvidencePack | None,
) -> OutlookResponse:
    pack_day = pack.as_of if pack else None
    stale = pack is None or (as_of - pack.as_of) > STALE_AFTER
    return OutlookResponse(
        as_of=pack_day or as_of,
        stale=stale,
        pack_id=pack.id if pack else None,
        pack_hash=pack.hash if pack else None,
        brief=None,
        news=[
            OutlookNews(
                title=item.title,
                publisher=item.publisher,
                published_at=item.published_at,
                category=item.category,
                url=item.url,
            )
            for item in news
        ],
        events=[
            OutlookEvent(
                date=item.date,
                title=item.title,
                kind=item.kind,
                ticker=item.ticker,
                source=item.source,
            )
            for item in events
        ],
        sources=sources,
    )


def outlook_from_store(
    session, *, as_of: date | None, now: datetime | None = None
) -> OutlookResponse:
    clock = now or datetime.now(ET)
    day = as_of or clock.date()
    pack = latest_evidence_pack(session, as_of)
    if pack is None and as_of is None:
        pack = latest_evidence_pack(session)
    sources = [
        OutlookSource(
            vendor=row.vendor,
            job_name=row.job_name,
            as_of=row.as_of,
            status=row.status,
            rows=row.rows,
            error=row.error,
        )
        for row in sources_from_counts(latest_jobs(session), store_counts(session))
    ]
    return build_outlook(
        as_of=day,
        now=clock,
        news=latest_news(session, since=clock - NEWS_SINCE, limit=NEWS_LIMIT),
        events=upcoming_events(session, start=day, end=day + timedelta(days=EVENTS_AHEAD_DAYS)),
        sources=sources,
        pack=pack,
    )
