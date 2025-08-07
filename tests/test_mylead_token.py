from pathlib import Path
import sys
import requests

sys.path.append(str(Path(__file__).resolve().parent.parent))
from get_mylead_token import fetch_mylead_token


def test_fetch_mylead_token_success(monkeypatch, capsys):
    monkeypatch.setenv("MYLEAD_USERNAME", "user")
    monkeypatch.setenv("MYLEAD_PASSWORD", "pass")

    class MockResponse:
        status_code = 200
        reason = "OK"

        def json(self):
            return {"access_token": "token123"}

        def raise_for_status(self):
            return None

    monkeypatch.setattr(requests, "post", lambda *a, **k: MockResponse())
    token = fetch_mylead_token()
    assert token == "token123"
    output = capsys.readouterr().out
    assert "✔️ MyLead login successful" in output


def test_fetch_mylead_token_request_error(monkeypatch, capsys):
    monkeypatch.setenv("MYLEAD_USERNAME", "user")
    monkeypatch.setenv("MYLEAD_PASSWORD", "pass")

    def raise_error(*args, **kwargs):
        raise requests.RequestException("network error")

    monkeypatch.setattr(requests, "post", raise_error)
    token = fetch_mylead_token()
    assert token is None
    output = capsys.readouterr().out
    assert "Login failed" in output
