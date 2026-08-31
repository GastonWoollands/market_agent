"""Ranked 1-day outliers and co-moves from stored series. No vendor I/O.

DEXJPUS is JPY per USD: a rise is a weaker yen. Do not invert in the UI.
Co-move payloads carry numbers only — no causal verbs. Optional `hint` is a
closed enum for the Outlook writer, not a Live badge.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from statistics import fmean, pstdev

WINDOW = 60
MIN_OBS = 20
Z_FLOOR = 1.5
MAX_OUTLIERS = 5
MIN_OUTLIERS = 3
HINTS = frozenset({"duration", "credit", "fx_jpy", "breadth", "vol", "front_long"})

Series = Sequence[tuple[date, float]]

MACRO_IDS = (
    "DGS2",
    "DGS10",
    "DGS30",
    "T10Y2Y",
    "VIXCLS",
    "DTWEXBGS",
    "DEXJPUS",
    "BAMLH0A0HYM2",
)
TAPE_IDS = ("^VIX", "UUP", "HYG", "LQD", "RSP", "SPY", "SMH", "IWM", "XLK", "XLU", "TLT")
YIELD_IDS = frozenset({"DGS2", "DGS10", "DGS30", "T10Y2Y", "BAMLH0A0HYM2"})

_THEMES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("fx_jpy", ("DEXJPUS", "SMH", "IWM", "^VIX", "VIXCLS")),
    ("vol", ("^VIX", "VIXCLS", "SMH", "IWM", "HYG")),
    ("duration", ("DGS10", "XLK", "XLU", "TLT")),
    ("front_long", ("DGS2", "DGS30", "T10Y2Y", "TLT")),
    ("credit", ("BAMLH0A0HYM2", "HYG", "IWM", "SMH", "^VIX", "VIXCLS")),
    ("breadth", ("IWM", "RSP", "SPY", "XLK")),
)


@dataclass(frozen=True)
class Outlier:
    id: str
    window: str
    change: float
    z: float


@dataclass(frozen=True)
class CoMove:
    ids: tuple[str, ...]
    window: str
    changes: dict[str, float]
    hint: str | None


def daily_changes(series: Series) -> list[tuple[date, float]]:
    ordered = sorted(series, key=lambda item: item[0])
    out: list[tuple[date, float]] = []
    for index in range(1, len(ordered)):
        prev = ordered[index - 1][1]
        last = ordered[index][1]
        day = ordered[index][0]
        if prev == 0:
            continue
        out.append((day, (last / prev - 1.0) * 100.0))
    return out


def yield_bp_changes(series: Series) -> list[tuple[date, float]]:
    ordered = sorted(series, key=lambda item: item[0])
    out: list[tuple[date, float]] = []
    for index in range(1, len(ordered)):
        prev = ordered[index - 1][1]
        last = ordered[index][1]
        out.append((ordered[index][0], (last - prev) * 100.0))
    return out


def trailing_z(changes: Series, *, window: int = WINDOW, min_obs: int = MIN_OBS) -> float | None:
    if not changes:
        return None
    values = [item[1] for item in sorted(changes, key=lambda item: item[0])[-window:]]
    if len(values) < min_obs:
        return None
    spread = pstdev(values)
    if spread == 0:
        return 0.0
    return (values[-1] - fmean(values)) / spread


def rank_drivers(
    series: Mapping[str, Series],
    *,
    yield_ids: Sequence[str] = tuple(YIELD_IDS),
) -> tuple[list[Outlier], list[CoMove]]:
    scored: list[Outlier] = []
    latest: dict[str, float] = {}
    z_by_id: dict[str, float] = {}
    yields = set(yield_ids)
    for name, points in series.items():
        if not points:
            continue
        changes = yield_bp_changes(points) if name in yields else daily_changes(points)
        if not changes:
            continue
        z_score = trailing_z(changes)
        if z_score is None:
            continue
        change = round(changes[-1][1], 4)
        latest[name] = change
        z_by_id[name] = z_score
        scored.append(Outlier(id=name, window="1d", change=change, z=round(z_score, 4)))
    scored.sort(key=lambda item: (-abs(item.z), item.id))
    strong = [item for item in scored if abs(item.z) >= Z_FLOOR]
    outliers = strong[:MAX_OUTLIERS] if strong else scored[:MIN_OUTLIERS]
    return outliers, _co_moves(z_by_id, latest)


def as_dicts(
    outliers: Sequence[Outlier], co_moves: Sequence[CoMove]
) -> tuple[list[dict], list[dict]]:
    return (
        [
            {"id": item.id, "window": item.window, "change": item.change, "z": item.z}
            for item in outliers
        ],
        [
            {
                "ids": list(item.ids),
                "window": item.window,
                "changes": dict(item.changes),
                "hint": item.hint,
            }
            for item in co_moves
        ],
    )


def _co_moves(z_by_id: Mapping[str, float], latest: Mapping[str, float]) -> list[CoMove]:
    out: list[CoMove] = []
    seen: set[tuple[str, ...]] = set()
    for hint, members in _THEMES:
        extreme = [name for name in members if abs(z_by_id.get(name, 0.0)) >= Z_FLOOR]
        if len(extreme) < 2:
            continue
        key = tuple(sorted(extreme))
        if key in seen:
            continue
        seen.add(key)
        out.append(
            CoMove(
                ids=key,
                window="1d",
                changes={name: round(latest[name], 4) for name in key if name in latest},
                hint=hint if hint in HINTS else None,
            )
        )
    return out
