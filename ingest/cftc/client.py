from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from ingest.cftc.errors import CftcHttpError, CftcParseError
from ingest.cftc.parse import COLUMNS, reports_from_rows
from ingest.http import JsonApiClient
from store.canonical import CotReport

PAGE = 5000


class CftcClient(JsonApiClient):
    """CFTC Public Reporting (Socrata), Traders in Financial Futures, futures only. No key."""

    base_url = "https://publicreporting.cftc.gov/resource"
    name = "CFTC"
    http_error = CftcHttpError
    parse_error = CftcParseError
    dataset = "gpe5-46if"

    def tff_reports(self, codes: Sequence[str], *, since: date) -> list[CotReport]:
        quoted = ", ".join(f"'{code}'" for code in codes)
        select = ", ".join(
            [
                "id",
                "cftc_contract_market_code",
                "market_and_exchange_names",
                "report_date_as_yyyy_mm_dd",
                "futonly_or_combined",
                *COLUMNS,
            ]
        )
        reports: list[CotReport] = []
        offset = 0
        while True:
            rows = self.get_json(
                f"/{self.dataset}.json",
                params={
                    "$select": select,
                    "$where": (
                        f"cftc_contract_market_code in ({quoted}) "
                        f"AND report_date_as_yyyy_mm_dd >= '{since.isoformat()}'"
                    ),
                    "$order": "report_date_as_yyyy_mm_dd, cftc_contract_market_code",
                    "$limit": PAGE,
                    "$offset": offset,
                },
            )
            reports.extend(reports_from_rows(rows))
            if len(rows) < PAGE:
                return reports
            offset += PAGE
