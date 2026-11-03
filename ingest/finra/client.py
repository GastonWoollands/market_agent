from __future__ import annotations

from datetime import date

from ingest.finra.errors import FinraHttpError, FinraParseError
from ingest.finra.parse import FIELDS, reports_from_rows, settlement_dates
from ingest.http import JsonApiClient
from store.canonical import ShortInterestReport

PAGE = 5000
# A name listed through every cycle; its rows reveal the settlement calendar.
CALENDAR_SYMBOL = "AAPL"


class FinraClient(JsonApiClient):
    """FINRA API Platform, public `otcMarket/consolidatedShortInterest`. No credential.

    Covers exchange-listed and OTC names, twice monthly (settlement ~mid and end of month,
    published about eight business days later).
    """

    base_url = "https://api.finra.org/data/group/otcMarket/name"
    name = "FINRA"
    http_error = FinraHttpError
    parse_error = FinraParseError
    dataset = "/consolidatedShortInterest"

    def settlement_dates(self, *, since: date, until: date) -> list[date]:
        rows = self.post_json(
            self.dataset,
            {
                "limit": 100,
                "fields": ["settlementDate"],
                "compareFilters": [
                    {
                        "compareType": "equal",
                        "fieldName": "symbolCode",
                        "fieldValue": CALENDAR_SYMBOL,
                    }
                ],
                "dateRangeFilters": [
                    {
                        "fieldName": "settlementDate",
                        "startDate": since.isoformat(),
                        "endDate": until.isoformat(),
                    }
                ],
            },
        )
        return settlement_dates(rows)

    def short_interest(self, settlement: date) -> list[ShortInterestReport]:
        """Every symbol for one settlement date (~22k rows, paged)."""
        reports: list[ShortInterestReport] = []
        offset = 0
        while True:
            rows = self.post_json(
                self.dataset,
                {
                    "limit": PAGE,
                    "offset": offset,
                    "fields": list(FIELDS),
                    "compareFilters": [
                        {
                            "compareType": "equal",
                            "fieldName": "settlementDate",
                            "fieldValue": settlement.isoformat(),
                        }
                    ],
                },
            )
            reports.extend(reports_from_rows(rows))
            if len(rows) < PAGE:
                return reports
            offset += PAGE
