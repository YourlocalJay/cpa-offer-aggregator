from pathlib import Path
import sys
import requests

sys.path.append(str(Path(__file__).resolve().parent.parent))
import get_mylead_token


def test_main_success(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("MYLEAD_USERNAME", "user")
    monkeypatch.setenv("MYLEAD_PASSWORD", "pass")
    monkeypatch.chdir(tmp_path)

    class MockResponse:
        status_code = 200
        reason = "OK"

        def json(self):
            return {"access_token": "token123"}

    monkeypatch.setattr(requests, "post", lambda *a, **k: MockResponse())
    get_mylead_token.main()

    token_file = tmp_path / "mylead_token.txt"
    assert token_file.read_text() == "token123"
    output = capsys.readouterr().out
    assert "✔️ MyLead login successful" in output


def test_main_request_error(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("MYLEAD_USERNAME", "user")
    monkeypatch.setenv("MYLEAD_PASSWORD", "pass")
    monkeypatch.chdir(tmp_path)

    def raise_error(*args, **kwargs):
        raise requests.RequestException("network error")

    monkeypatch.setattr(requests, "post", raise_error)
    get_mylead_token.main()

    token_file = tmp_path / "mylead_token.txt"
    assert not token_file.exists()
    output = capsys.readouterr().out
    assert "Login failed" in output
