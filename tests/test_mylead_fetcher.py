from pathlib import Path
import sys
import requests

sys.path.append(str(Path(__file__).resolve().parent.parent))
from fetchers.mylead_fetcher import fetch_mylead_offers


def test_fetch_mylead_offers_success(monkeypatch):
    monkeypatch.setenv("MYLEAD_TOKEN", "token123")

    class MockResponse:
        def json(self):
            return {
                "data": [
                    {
                        "name": "Offer 1",
                        "tracking_url": "http://example.com",
                        "geos": ["US", "US"],
                        "device": "mobile",
                        "payout": "2.5",
                        "category": "Games",
                        "allowed_traffic": ["social"],
                        "requirements": "No login",
                    },
                    {
                        "name": "Bad Offer",
                        "tracking_url": "",
                    },
                ]
            }

        def raise_for_status(self):
            return None

    monkeypatch.setattr(requests, "get", lambda *a, **k: MockResponse())
    offers = fetch_mylead_offers()
    assert len(offers) == 1
    offer = offers[0]
    assert offer["name"] == "Offer 1"
    assert offer["geo"] == ["US"]
    assert offer["device"] == "Android"
    assert offer["payout"] == 2.5


def test_fetch_mylead_offers_missing_token(monkeypatch):
    monkeypatch.delenv("MYLEAD_TOKEN", raising=False)
    offers = fetch_mylead_offers()
    assert offers == []


def test_fetch_mylead_offers_request_error(monkeypatch):
    monkeypatch.setenv("MYLEAD_TOKEN", "token123")

    def raise_error(*args, **kwargs):
        raise requests.RequestException("network error")

    monkeypatch.setattr(requests, "get", raise_error)
    offers = fetch_mylead_offers()
    assert offers == []
