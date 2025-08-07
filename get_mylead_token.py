import os
import requests

API_URL = "https://api.mylead.eu/api/external/v1/auth/login"

def main() -> None:
    username = os.environ.get("MYLEAD_USERNAME")
    password = os.environ.get("MYLEAD_PASSWORD")
    if not username or not password:
        print("❌ Missing MyLead credentials")
        return

    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {"username": username, "password": password}

    try:
        response = requests.post(API_URL, headers=headers, data=data, timeout=10)
    except requests.RequestException as exc:  # network-related errors
        print(f"❌ Login failed: {exc}")
        return

    if response.status_code == 200:
        try:
            token = response.json().get("access_token")
        except ValueError:
            print("❌ Login failed: Invalid JSON response")
            return
        if not token:
            print("❌ Login failed: access_token not found in response")
            return
        with open("mylead_token.txt", "w", encoding="utf-8") as f:
            f.write(token)
        print("✔️ MyLead login successful")
        print("✔️ Access token saved to mylead_token.txt")
    else:
        print(f"❌ Login failed: {response.status_code} {response.reason}")


if __name__ == "__main__":
    main()
