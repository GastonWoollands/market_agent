from __future__ import annotations

import json
from pathlib import Path
from zipfile import ZipFile

import httpx

from ingest.retry import http_get
from ingest.sec.errors import SecError, SecHttpError, SecParseError
from ingest.sec.parse import pad_cik, tickers_from_payload, ttm_from_facts
from ingest.yahoo.rate_limit import TokenBucket
from store.canonical import MetricTtm, SecTicker
from store.settings import REPO_ROOT

TICKERS_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
FACTS_ZIP_URLS = (
    "https://www.sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip",
    "https://data.sec.gov/archives/edgar/daily-index/xbrl/companyfacts.zip",
)
FACTS_JSON_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
DEFAULT_CACHE = REPO_ROOT / "data" / "sec"


class CompanyFactsArchive:
    """Read CIK JSON out of the official companyfacts.zip bulk file."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._zip = ZipFile(path)
        self._names = {Path(name).name.upper(): name for name in self._zip.namelist()}

    def close(self) -> None:
        self._zip.close()

    def __enter__(self) -> CompanyFactsArchive:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def load(self, cik: str) -> dict | None:
        padded = pad_cik(cik)
        for key in (f"CIK{padded}.JSON", f"{padded}.JSON"):
            name = self._names.get(key)
            if name is None:
                continue
            with self._zip.open(name) as handle:
                payload = json.load(handle)
            if not isinstance(payload, dict):
                raise SecParseError(f"{padded}: zip member is not an object")
            return payload
        return None


class SecClient:
    """Official EDGAR tickers + companyfacts. Do not scrape EDGAR HTML or add edgartools."""

    def __init__(
        self,
        user_agent: str,
        *,
        rate: float = 8.0,
        timeout: float = 60.0,
        client: httpx.Client | None = None,
        cache_dir: Path | None = None,
    ) -> None:
        ua = user_agent.strip()
        if not ua:
            raise SecError("SEC_USER_AGENT is missing")
        self._bucket = TokenBucket(rate=rate, burst=10)
        self._owns_client = client is None
        self._cache = cache_dir or DEFAULT_CACHE
        self._http = client or httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={
                "User-Agent": ua,
                "Accept-Encoding": "gzip, deflate",
                "Accept": "application/json, application/zip, */*",
            },
        )

    def close(self) -> None:
        if self._owns_client:
            self._http.close()

    def __enter__(self) -> SecClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def fetch_tickers(self, *, exchanges: list[str]) -> list[SecTicker]:
        payload = self._get_json(TICKERS_URL)
        return tickers_from_payload(payload, exchanges=exchanges)

    def ensure_facts_zip(self, *, refresh: bool = False) -> Path:
        self._cache.mkdir(parents=True, exist_ok=True)
        path = self._cache / "companyfacts.zip"
        if path.exists() and path.stat().st_size > 1_000_000 and not refresh:
            return path
        last_error: Exception | None = None
        tmp = path.with_suffix(".zip.part")
        for url in FACTS_ZIP_URLS:
            try:
                self._download(url, tmp)
            except (SecHttpError, httpx.HTTPError) as exc:
                last_error = exc
                continue
            tmp.replace(path)
            return path
        raise SecHttpError(f"companyfacts.zip download failed ({last_error})")

    def fetch_companyfacts(self, cik: str) -> dict:
        padded = pad_cik(cik)
        payload = self._get_json(FACTS_JSON_URL.format(cik=padded))
        if not isinstance(payload, dict):
            raise SecParseError(f"{padded}: companyfacts is not an object")
        return payload

    def metric_from_archive(
        self, archive: CompanyFactsArchive, cik: str, *, require_quarters: bool = False
    ) -> MetricTtm | None:
        payload = archive.load(cik)
        if payload is None:
            return None
        return ttm_from_facts(payload, require_quarters=require_quarters)

    def _get_json(self, url: str) -> object:
        try:
            response = http_get(self._http, self._bucket, url)
        except httpx.HTTPError as exc:
            raise SecHttpError(f"request failed ({exc.__class__.__name__})") from exc
        self._raise_http(response)
        try:
            return response.json()
        except ValueError as exc:
            raise SecParseError("response is not JSON") from exc

    def _download(self, url: str, dest: Path) -> None:
        self._bucket.acquire()
        with self._http.stream("GET", url, timeout=600.0) as response:
            self._raise_http(response)
            with dest.open("wb") as handle:
                for chunk in response.iter_bytes():
                    handle.write(chunk)
        if dest.stat().st_size < 1_000_000:
            dest.unlink(missing_ok=True)
            raise SecHttpError(f"{url}: zip too small")

    def _raise_http(self, response: httpx.Response) -> None:
        if response.status_code == 429:
            raise SecHttpError("SEC rate limited", status_code=429)
        if response.status_code == 403:
            raise SecHttpError(
                "SEC forbidden — set SEC_USER_AGENT to 'MarketAgent you@real-email'",
                status_code=403,
            )
        if response.status_code >= 400:
            raise SecHttpError(f"HTTP {response.status_code}", status_code=response.status_code)
