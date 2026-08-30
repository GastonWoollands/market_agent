from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def test_watchlist_preflight_allows_ipv6_loopback_and_private_network() -> None:
    response = client.options(
        "/watchlist",
        headers={
            "Origin": "http://[::1]:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
            "Access-Control-Request-Private-Network": "true",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://[::1]:3000"
    assert response.headers["access-control-allow-private-network"] == "true"


def test_watchlist_delete_preflight_allows_localhost() -> None:
    response = client.options(
        "/watchlist/AAPL",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "DELETE",
            "Access-Control-Request-Private-Network": "true",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
