from decimal import Decimal

import pytest

from ingest.fred.errors import FredParseError
from ingest.fred.parse import observations_from_payload


def test_observations_skip_missing_dots() -> None:
    points = observations_from_payload(
        "DGS10",
        {
            "observations": [
                {"date": "2026-08-13", "value": "4.20"},
                {"date": "2026-08-14", "value": "."},
                {"date": "2026-08-15", "value": "4.25"},
            ]
        },
    )
    assert [point.date.isoformat() for point in points] == ["2026-08-13", "2026-08-15"]
    assert points[-1].value == Decimal("4.25")
    assert points[-1].series_id == "DGS10"


def test_observations_reject_error_payload() -> None:
    with pytest.raises(FredParseError, match="invalid"):
        observations_from_payload(
            "DGS10",
            {"error_code": 400, "error_message": "invalid api_key"},
        )


def test_observations_reject_empty() -> None:
    with pytest.raises(FredParseError, match="no usable"):
        observations_from_payload("DGS10", {"observations": [{"date": "2026-08-14", "value": "."}]})
