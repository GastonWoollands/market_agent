from datetime import date
from decimal import Decimal

from ingest.sec.parse import (
    fresh_ttm,
    fy_history_from_facts,
    tickers_from_payload,
    ttm_from_facts,
    ttm_history_from_facts,
    usable_ttm,
    yahoo_symbol,
)


def test_yahoo_symbol_maps_share_classes() -> None:
    assert yahoo_symbol("BRK.B") == "BRK-B"
    assert yahoo_symbol("aapl") == "AAPL"


def test_tickers_exchange_filters_nyse_nasdaq() -> None:
    payload = {
        "fields": ["cik", "name", "ticker", "exchange"],
        "data": [
            [320193, "Apple Inc.", "AAPL", "Nasdaq"],
            [1046179, "Southwest Airlines", "LUV", "NYSE"],
            [1045810, "NVIDIA", "NVDA", "Nasdaq"],
            [1067983, "Berkshire Hathaway", "BRK-B", "NYSE"],
            [1067983, "Berkshire Hathaway", "BRK-A", "NYSE"],
            [123456, "Some ETF", "SPY", "NYSE ARCA"],
            [2, "Unit", "ABCD.U", "NYSE American"],
        ],
    }
    rows = tickers_from_payload(payload, exchanges=["NYSE", "Nasdaq", "NYSE American"])
    tickers = {item.ticker for item in rows}
    assert {"AAPL", "LUV", "NVDA", "BRK-B", "BRK-A"} <= tickers
    assert "SPY" not in tickers
    assert "ABCD.U" not in tickers
    by_ticker = {item.ticker: item for item in rows}
    assert by_ticker["AAPL"].cik == "0000320193"
    assert by_ticker["AAPL"].exchange == "Nasdaq"


def test_ttm_sums_last_four_quarters() -> None:
    payload = {
        "cik": 320193,
        "facts": {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "units": {
                        "USD": [
                            _q("2025-04-01", "2025-06-30", 90_000_000_000, "10-Q"),
                            _q("2025-01-01", "2025-03-31", 80_000_000_000, "10-Q"),
                            _q("2024-10-01", "2024-12-31", 70_000_000_000, "10-K"),
                            _q("2024-07-01", "2024-09-30", 60_000_000_000, "10-Q"),
                            _q("2024-04-01", "2024-06-30", 10_000_000_000, "10-Q"),
                            {
                                "start": "2024-01-01",
                                "end": "2024-12-31",
                                "val": 999_000_000_000,
                                "form": "10-K",
                            },
                        ]
                    }
                },
                "OperatingIncomeLoss": {
                    "units": {
                        "USD": [
                            _q("2025-04-01", "2025-06-30", 10_000_000_000, "10-Q"),
                            _q("2025-01-01", "2025-03-31", 10_000_000_000, "10-Q"),
                            _q("2024-10-01", "2024-12-31", 10_000_000_000, "10-K"),
                            _q("2024-07-01", "2024-09-30", 10_000_000_000, "10-Q"),
                        ]
                    }
                },
                "DepreciationAndAmortization": {
                    "units": {
                        "USD": [
                            _q("2025-04-01", "2025-06-30", 1_000_000_000, "10-Q"),
                            _q("2025-01-01", "2025-03-31", 1_000_000_000, "10-Q"),
                            _q("2024-10-01", "2024-12-31", 1_000_000_000, "10-K"),
                            _q("2024-07-01", "2024-09-30", 1_000_000_000, "10-Q"),
                        ]
                    }
                },
            }
        },
    }
    metric = ttm_from_facts(payload)
    assert metric is not None
    assert metric.cik == "0000320193"
    assert metric.revenue == Decimal("300000000000")
    assert metric.as_of == date(2025, 6, 30)
    assert metric.ebitda == Decimal("44000000000")
    assert not usable_ttm(metric)


def test_ttm_falls_back_to_annual_and_rejects_sub_billion() -> None:
    small = {
        "cik": 1,
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            {
                                "start": "2024-01-01",
                                "end": "2024-12-31",
                                "val": 400_000_000,
                                "form": "10-K",
                            }
                        ]
                    }
                }
            }
        },
    }
    metric = ttm_from_facts(small)
    assert metric is not None
    assert metric.revenue == Decimal("400000000")
    assert ttm_from_facts(small, require_quarters=True) is None
    empty = {"cik": 2, "facts": {"us-gaap": {}}}
    assert ttm_from_facts(empty) is None


def test_usable_ttm_requires_positive_ebitda_and_ev_inputs() -> None:
    metric = ttm_from_facts(_ev_payload())
    assert metric is not None
    assert usable_ttm(metric)
    assert metric.fcf is not None
    missing_shares = ttm_from_facts(_ev_payload(shares=None))
    assert missing_shares is not None
    assert not usable_ttm(missing_shares)
    loss = ttm_from_facts(_ev_payload(ebit=-2_000_000_000))
    assert loss is not None
    assert loss.ebitda is not None and loss.ebitda < 0
    assert not usable_ttm(loss)


def test_flow_ttm_prefers_current_quarters_over_stale_annual() -> None:
    payload = {
        "cik": 1,
        "facts": {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "units": {
                        "USD": [
                            {
                                "start": "2014-01-01",
                                "end": "2014-12-31",
                                "val": 50_000_000_000,
                                "form": "10-K",
                            }
                        ]
                    }
                },
                "Revenues": {
                    "units": {
                        "USD": [
                            _q("2025-04-01", "2025-06-30", 10_000_000_000, "10-Q"),
                            _q("2025-01-01", "2025-03-31", 10_000_000_000, "10-Q"),
                            _q("2024-10-01", "2024-12-31", 10_000_000_000, "10-K"),
                            _q("2024-07-01", "2024-09-30", 10_000_000_000, "10-Q"),
                        ]
                    }
                },
            }
        },
    }
    metric = ttm_from_facts(payload, require_quarters=True)
    assert metric is not None
    assert metric.revenue == Decimal("40000000000")
    assert metric.as_of == date(2025, 6, 30)
    assert not fresh_ttm(metric, today=date(2026, 8, 18), max_age_days=30)
    assert fresh_ttm(metric, today=date(2026, 8, 18))


def test_ebitda_sums_split_depreciation_and_amortization() -> None:
    quarters = [
        _q("2025-04-01", "2025-06-30", 8_000_000_000, "10-Q"),
        _q("2025-01-01", "2025-03-31", 8_000_000_000, "10-Q"),
        _q("2024-10-01", "2024-12-31", 8_000_000_000, "10-K"),
        _q("2024-07-01", "2024-09-30", 8_000_000_000, "10-Q"),
    ]
    payload = {
        "cik": 789019,
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            _q("2025-04-01", "2025-06-30", 70_000_000_000, "10-Q"),
                            _q("2025-01-01", "2025-03-31", 70_000_000_000, "10-Q"),
                            _q("2024-10-01", "2024-12-31", 70_000_000_000, "10-K"),
                            _q("2024-07-01", "2024-09-30", 70_000_000_000, "10-Q"),
                        ]
                    }
                },
                "OperatingIncomeLoss": {"units": {"USD": quarters}},
                "Depreciation": {
                    "units": {
                        "USD": [
                            _q(q["start"], q["end"], 2_000_000_000, q["form"]) for q in quarters
                        ]
                    }
                },
                "AmortizationOfIntangibleAssets": {
                    "units": {
                        "USD": [
                            _q(q["start"], q["end"], 1_000_000_000, q["form"]) for q in quarters
                        ]
                    }
                },
                "NetCashProvidedByUsedInOperatingActivities": {
                    "units": {
                        "USD": [
                            _q(q["start"], q["end"], 12_000_000_000, q["form"]) for q in quarters
                        ]
                    }
                },
                "PaymentsToAcquirePropertyPlantAndEquipment": {
                    "units": {
                        "USD": [
                            _q(q["start"], q["end"], 3_000_000_000, q["form"]) for q in quarters
                        ]
                    }
                },
                "LongTermDebt": {"units": {"USD": [_instant("2025-06-30", 5_000_000_000)]}},
                "CashAndCashEquivalentsAtCarryingValue": {
                    "units": {"USD": [_instant("2025-06-30", 1_000_000_000)]}
                },
            },
            "dei": {
                "EntityCommonStockSharesOutstanding": {
                    "units": {"shares": [_instant("2025-06-30", 7_000_000_000)]}
                }
            },
        },
    }
    metric = ttm_from_facts(payload, require_quarters=True)
    assert metric is not None
    assert metric.ebitda == Decimal("44000000000")
    assert usable_ttm(metric)


def test_shares_fall_back_to_weighted_average() -> None:
    payload = _ev_payload(shares=None)
    payload["facts"]["us-gaap"]["WeightedAverageNumberOfSharesOutstandingBasic"] = {
        "units": {
            "shares": [
                {
                    "start": "2025-04-01",
                    "end": "2025-06-30",
                    "val": 2_500_000_000,
                    "form": "10-Q",
                },
                {
                    "start": "2025-01-01",
                    "end": "2025-06-30",
                    "val": 2_400_000_000,
                    "form": "10-Q",
                },
            ]
        }
    }
    metric = ttm_from_facts(payload, require_quarters=True)
    assert metric is not None
    assert metric.shares == Decimal("2500000000")
    assert usable_ttm(metric)


def test_ttm_history_keeps_complete_windows_only() -> None:
    payload = _ev_payload()
    rows = ttm_history_from_facts(payload, today=date(2026, 8, 18), years=5)
    assert [item.as_of for item in rows] == [date(2025, 6, 30)]
    assert ttm_from_facts(payload, require_quarters=True, through=date(2025, 3, 31)) is None


def test_fy_history_reads_annuals_and_cogs_gross_profit() -> None:
    payload = _fy_payload()
    rows = fy_history_from_facts(payload, today=date(2026, 9, 14), years=6)
    assert [item.as_of for item in rows] == [
        date(2023, 9, 30),
        date(2024, 9, 28),
        date(2025, 9, 27),
    ]
    latest = rows[-1]
    assert latest.fiscal_year == 2025
    assert latest.revenue == Decimal("150000000000")
    assert latest.net_income == Decimal("30000000000")
    assert latest.cfo == Decimal("40000000000")
    assert latest.gross_profit == Decimal("70000000000")
    assert latest.total_assets == Decimal("350000000000")
    assert latest.long_term_debt == Decimal("80000000000")
    assert latest.shares == Decimal("15000000000")


def test_fy_prefers_noncurrent_long_term_debt() -> None:
    payload = _fy_payload()
    payload["facts"]["us-gaap"]["LongTermDebt"] = {
        "units": {"USD": [_instant("2025-09-27", 99_000_000_000, "10-K")]}
    }
    rows = fy_history_from_facts(payload, today=date(2026, 9, 14))
    assert rows[-1].long_term_debt == Decimal("80000000000")


def _q(start: str, end: str, val: int, form: str) -> dict[str, object]:
    return {"start": start, "end": end, "val": val, "form": form}


def _instant(end: str, val: int, form: str = "10-Q") -> dict[str, object]:
    return {"end": end, "val": val, "form": form}


def _ev_payload(*, shares: int | None = 1_000_000_000, ebit: int = 10_000_000_000) -> dict:
    quarters = [
        _q("2025-04-01", "2025-06-30", ebit, "10-Q"),
        _q("2025-01-01", "2025-03-31", ebit, "10-Q"),
        _q("2024-10-01", "2024-12-31", ebit, "10-K"),
        _q("2024-07-01", "2024-09-30", ebit, "10-Q"),
    ]
    da = [_q(item["start"], item["end"], 1_000_000_000, item["form"]) for item in quarters]
    facts: dict = {
        "us-gaap": {
            "Revenues": {"units": {"USD": [
                _q("2025-04-01", "2025-06-30", 20_000_000_000, "10-Q"),
                _q("2025-01-01", "2025-03-31", 20_000_000_000, "10-Q"),
                _q("2024-10-01", "2024-12-31", 20_000_000_000, "10-K"),
                _q("2024-07-01", "2024-09-30", 20_000_000_000, "10-Q"),
            ]}},
            "OperatingIncomeLoss": {"units": {"USD": quarters}},
            "DepreciationAndAmortization": {"units": {"USD": da}},
            "NetCashProvidedByUsedInOperatingActivities": {"units": {"USD": da}},
            "PaymentsToAcquirePropertyPlantAndEquipment": {
                "units": {
                    "USD": [_q(q["start"], q["end"], 200_000_000, q["form"]) for q in quarters]
                }
            },
            "LongTermDebt": {"units": {"USD": [_instant("2025-06-30", 5_000_000_000)]}},
            "CashAndCashEquivalentsAtCarryingValue": {
                "units": {"USD": [_instant("2025-06-30", 1_000_000_000)]}
            },
        }
    }
    if shares is not None:
        facts["dei"] = {
            "EntityCommonStockSharesOutstanding": {
                "units": {"shares": [_instant("2025-06-30", shares)]}
            }
        }
    return {"cik": 320193, "facts": facts}


def _annual(start: str, end: str, val: int) -> dict[str, object]:
    return {"start": start, "end": end, "val": val, "form": "10-K"}


def _fy_payload() -> dict:
    years = [
        ("2022-10-01", "2023-09-30", 100_000_000_000, 20_000_000_000, 25_000_000_000),
        ("2023-10-01", "2024-09-28", 120_000_000_000, 24_000_000_000, 32_000_000_000),
        ("2024-10-01", "2025-09-27", 150_000_000_000, 30_000_000_000, 40_000_000_000),
    ]
    revenue = [_annual(start, end, rev) for start, end, rev, _ni, _cfo in years]
    ni = [_annual(start, end, ni) for start, end, _rev, ni, _cfo in years]
    cfo = [_annual(start, end, cfo) for start, end, _rev, _ni, cfo in years]
    cogs = [_annual(start, end, 80_000_000_000) for start, end, _rev, _ni, _cfo in years]
    ebit = [_annual(start, end, 35_000_000_000) for start, end, _rev, _ni, _cfo in years]
    instants = [
        _instant("2023-09-30", 250_000_000_000, "10-K"),
        _instant("2024-09-28", 300_000_000_000, "10-K"),
        _instant("2025-09-27", 350_000_000_000, "10-K"),
    ]
    current = [
        _instant("2023-09-30", 100_000_000_000, "10-K"),
        _instant("2024-09-28", 120_000_000_000, "10-K"),
        _instant("2025-09-27", 140_000_000_000, "10-K"),
    ]
    cl = [
        _instant("2023-09-30", 50_000_000_000, "10-K"),
        _instant("2024-09-28", 55_000_000_000, "10-K"),
        _instant("2025-09-27", 60_000_000_000, "10-K"),
    ]
    ltd = [
        _instant("2023-09-30", 90_000_000_000, "10-K"),
        _instant("2024-09-28", 85_000_000_000, "10-K"),
        _instant("2025-09-27", 80_000_000_000, "10-K"),
    ]
    liab = [
        _instant("2023-09-30", 140_000_000_000, "10-K"),
        _instant("2024-09-28", 140_000_000_000, "10-K"),
        _instant("2025-09-27", 140_000_000_000, "10-K"),
    ]
    equity = [
        _instant("2023-09-30", 110_000_000_000, "10-K"),
        _instant("2024-09-28", 160_000_000_000, "10-K"),
        _instant("2025-09-27", 210_000_000_000, "10-K"),
    ]
    re = [
        _instant("2023-09-30", 80_000_000_000, "10-K"),
        _instant("2024-09-28", 100_000_000_000, "10-K"),
        _instant("2025-09-27", 130_000_000_000, "10-K"),
    ]
    shares = [
        _instant("2023-09-30", 15_000_000_000, "10-K"),
        _instant("2024-09-28", 15_000_000_000, "10-K"),
        _instant("2025-09-27", 15_000_000_000, "10-K"),
    ]
    return {
        "cik": 320193,
        "facts": {
            "us-gaap": {
                "Revenues": {"units": {"USD": revenue}},
                "NetIncomeLoss": {"units": {"USD": ni}},
                "NetCashProvidedByUsedInOperatingActivities": {"units": {"USD": cfo}},
                "CostOfGoodsSold": {"units": {"USD": cogs}},
                "OperatingIncomeLoss": {"units": {"USD": ebit}},
                "Assets": {"units": {"USD": instants}},
                "AssetsCurrent": {"units": {"USD": current}},
                "LiabilitiesCurrent": {"units": {"USD": cl}},
                "LongTermDebtNoncurrent": {"units": {"USD": ltd}},
                "Liabilities": {"units": {"USD": liab}},
                "StockholdersEquity": {"units": {"USD": equity}},
                "RetainedEarningsAccumulatedDeficit": {"units": {"USD": re}},
            },
            "dei": {
                "EntityCommonStockSharesOutstanding": {"units": {"shares": shares}},
            },
        },
    }
