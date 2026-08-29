from datetime import date, timedelta

from analytics.drivers import as_dicts, rank_drivers


def _series(start: date, values: list[float]) -> list[tuple[date, float]]:
    return [(start + timedelta(days=index), value) for index, value in enumerate(values)]


def _quiet(start: float, n: int = 80) -> list[float]:
    return [start + (0.01 if index % 2 == 0 else -0.01) for index in range(n)]


def test_rank_drivers_quiet_day_still_emits() -> None:
    start = date(2026, 1, 1)
    series = {
        "SMH": _series(start, _quiet(100)),
        "IWM": _series(start, _quiet(200)),
        "XLK": _series(start, _quiet(50)),
    }
    outliers, co_moves = rank_drivers(series)
    assert len(outliers) == 3
    assert all(item.window == "1d" for item in outliers)
    assert co_moves == []


def test_rank_drivers_yen_smh_vix_co_move_has_numbers_no_verbs() -> None:
    start = date(2026, 1, 1)
    yen = _quiet(150.0)
    yen[-1] = 140.0
    smh = _quiet(100.0)
    smh[-1] = 90.0
    vix = _quiet(15.0)
    vix[-1] = 22.0
    series = {
        "DEXJPUS": _series(start, yen),
        "SMH": _series(start, smh),
        "^VIX": _series(start, vix),
        "XLK": _series(start, _quiet(80.0)),
    }
    outliers, co_moves = rank_drivers(series)
    ids = {item.id for item in outliers}
    assert {"DEXJPUS", "SMH", "^VIX"} <= ids
    assert any(abs(item.z) >= 1.5 for item in outliers)
    assert co_moves
    move = next(item for item in co_moves if item.hint == "fx_jpy")
    assert set(move.ids) >= {"DEXJPUS", "SMH", "^VIX"}
    assert move.changes["DEXJPUS"] < 0
    assert move.changes["SMH"] < 0
    assert move.changes["^VIX"] > 0
    blob = str(as_dicts(outliers, co_moves))
    for verb in ("caused", "unwind", "triggered", "because"):
        assert verb not in blob.lower()


def test_rank_drivers_yields_use_bp_change() -> None:
    start = date(2026, 1, 1)
    values = [4.20] * 80
    values[-1] = 4.45
    outliers, _co_moves = rank_drivers({"DGS10": _series(start, values)})
    assert outliers[0].id == "DGS10"
    assert outliers[0].change == 25.0
