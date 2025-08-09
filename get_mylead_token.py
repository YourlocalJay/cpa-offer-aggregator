import os
from pathlib import Path

import requests

API_URL = os.environ.get("MYLEAD_LOGIN_URL", "https://api.mylead.eu/api/external/v1/auth/login")


def fetch_mylead_token() -> str | None:
    """Authenticate with the MyLead API and return an access token."""
    username = os.environ.get("MYLEAD_USERNAME")
    password = os.environ.get("MYLEAD_PASSWORD")
    if not username or not password:
        print("❌ Missing MyLead credentials")
        return None

    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {"username": username, "password": password}

    try:
        response = requests.post(API_URL, headers=headers, data=data, timeout=10)
        response.raise_for_status()
    except requests.RequestException as exc:  # network-related errors
        print(f"❌ Login failed: {exc}")
        return None

    try:
        json_response = response.json()
    except ValueError:
        print("❌ Login failed: Invalid JSON response")
        return None

    token = (
        json_response.get("access_token")
        or json_response.get("token")
        or (json_response.get("data") or {}).get("token")
    )

    if not token:
        print(f"❌ Login failed: access_token not found in response (status code {response.status_code})")
        print(f"Response body (truncated): {response.text[:400]!r}")
        return None

    token_path = Path(__file__).with_name("mylead_token.txt")
    try:
        token_path.write_text(token)
    except OSError as exc:
        print(f"❌ Failed to write token file: {exc}")
        return None

    print("✔️ MyLead login successful")
    return token


if __name__ == "__main__":
    if fetch_mylead_token() is None:
        raise SystemExit(1)
