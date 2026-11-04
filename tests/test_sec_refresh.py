import os
import time
from pathlib import Path

import pytest

from ingest.sec.client import SecClient
from ingest.sec.errors import SecHttpError
from jobs.ingest_sec import RunPlan, Tally, plan_run


def _plan(**overrides: object) -> RunPlan:
    args: dict[str, object] = {
        "rebuild": False,
        "fy_only": False,
        "members": 973,
        "tickers": None,
        "limit": None,
        "zip_flags": False,
    }
    args.update(overrides)
    return plan_run(**args)  # type: ignore[arg-type]


def test_default_is_a_full_refresh_that_never_touches_membership() -> None:
    plan = _plan()
    assert plan == RunPlan("refresh", full=True)
    assert plan.dates_dataset is True
    assert plan.enforce_band is False


def test_only_a_full_rebuild_enforces_the_band() -> None:
    assert _plan(rebuild=True).enforce_band is True
    assert _plan(rebuild=True, tickers={"AAPL"}).enforce_band is False


def test_partial_and_fy_only_runs_do_not_date_the_dataset() -> None:
    assert _plan(tickers={"AAPL"}).dates_dataset is False
    assert _plan(limit=5).dates_dataset is False
    assert _plan(fy_only=True).dates_dataset is False


def test_refresh_rejects_zip_flags_and_an_empty_universe() -> None:
    with pytest.raises(RuntimeError, match="--rebuild or --fy-only"):
        _plan(zip_flags=True)
    with pytest.raises(RuntimeError, match="--rebuild"):
        _plan(members=0)
    assert _plan(members=0, rebuild=True, tickers={"AAPL"}).mode == "rebuild"


def test_mass_fetch_failures_block_the_data_date() -> None:
    assert Tally(listed=973, fetch_failed=40).fetch_ok_enough() is True
    assert Tally(listed=973, fetch_failed=600).fetch_ok_enough() is False
    assert Tally(listed=0).fetch_ok_enough() is False


def _client_with_zip(
    tmp_path: Path, age_days: float, *, fail: bool = False
) -> tuple[SecClient, list[str]]:
    path = tmp_path / "companyfacts.zip"
    path.write_bytes(b"x" * 1_000_001)
    stamp = time.time() - age_days * 86400
    os.utime(path, (stamp, stamp))
    client = SecClient("test test@example.com", cache_dir=tmp_path)
    downloads: list[str] = []

    def fake_download(url: str, dest: Path) -> None:
        downloads.append(url)
        if fail:
            raise SecHttpError("503", status_code=503)
        dest.write_bytes(b"y" * 1_000_001)

    client._download = fake_download  # type: ignore[method-assign]
    return client, downloads


def test_recent_zip_is_reused(tmp_path: Path) -> None:
    client, downloads = _client_with_zip(tmp_path, age_days=2)
    with client:
        client.ensure_facts_zip()
    assert downloads == []


def test_old_zip_is_downloaded_again(tmp_path: Path) -> None:
    client, downloads = _client_with_zip(tmp_path, age_days=78)
    with client:
        path = client.ensure_facts_zip()
    assert len(downloads) == 1
    assert path.read_bytes()[:1] == b"y"


def test_old_zip_is_kept_when_every_download_fails(tmp_path: Path) -> None:
    client, downloads = _client_with_zip(tmp_path, age_days=78, fail=True)
    with client:
        path = client.ensure_facts_zip()
    assert len(downloads) == 2
    assert path.read_bytes()[:1] == b"x"
