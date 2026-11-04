import os
import time
from pathlib import Path

import pytest

from ingest.sec.client import SecClient
from jobs.ingest_sec import run_mode


def test_run_mode_defaults_to_refresh_of_stored_names() -> None:
    assert run_mode(rebuild=False, fy_only=False, members=973) == "refresh"
    assert run_mode(rebuild=True, fy_only=False, members=973) == "rebuild"
    assert run_mode(rebuild=True, fy_only=True, members=973) == "fy_only"


def test_run_mode_refuses_refresh_of_an_empty_universe() -> None:
    with pytest.raises(RuntimeError, match="--rebuild"):
        run_mode(rebuild=False, fy_only=False, members=0)


def _client_with_zip(tmp_path: Path, age_days: float) -> tuple[SecClient, list[str]]:
    path = tmp_path / "companyfacts.zip"
    path.write_bytes(b"x" * 1_000_001)
    stamp = time.time() - age_days * 86400
    os.utime(path, (stamp, stamp))
    client = SecClient("test test@example.com", cache_dir=tmp_path)
    downloads: list[str] = []

    def fake_download(url: str, dest: Path) -> None:
        downloads.append(url)
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
