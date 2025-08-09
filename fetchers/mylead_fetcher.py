"""
MyLead Offer Fetcher (hardened, env‑configurable)
=================================================

- Reads API base/path from environment:
    MYLEAD_API_BASE   (default: https://api.mylead.global/v2)
    MYLEAD_OFFERS_PATH (default: /offers)

- Auth token comes from:
    1) env MYLEAD_TOKEN
    2) file mylead_token.txt (repo root)

- Robust response handling:
    Accepts top-level list OR {data:[...]} OR {offers:[...]}.

- Retry + backoff on transient errors.
- Clear debug logs on HTTP/JSON issues.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from utils.logging import setup_logger

logger = setup_logger(__name__)

# ----------------------------
# Configuration
# ----------------------------
MYLEAD_API_BASE = os.getenv("MYLEAD_API_BASE", "https://api.mylead.global/v2").rstrip("/")
MYLEAD_OFFERS_PATH = os.getenv("MYLEAD_OFFERS_PATH", "/offers")
MYLEAD_API_URL = f"{MYLEAD_API_BASE}{MYLEAD_OFFERS_PATH}"

MYLEAD_API_TIMEOUT = 30  # seconds
MAX_RETRIES = 3
RATE_LIMIT_DELAY = 1  # seconds between retries


# ----------------------------
# Token loading
# ----------------------------
def load_mylead_token() -> Optional[str]:
    """Return a MyLead API token.

    Preference order:
      1) Environment variable MYLEAD_TOKEN
      2) Local file mylead_token.txt (project root)
    Returns None if not found (callers should handle gracefully).
    """
    env_token = os.getenv("MYLEAD_TOKEN")
    if env_token:
        return env_token.strip()

    token_path = Path(__file__).resolve().parent.parent / "mylead_token.txt"
    try:
        return token_path.read_text(encoding="utf-8").strip()
    except OSError:
        logger.error("❌ mylead_token.txt not found and MYLEAD_TOKEN not set.")
        return None


# ----------------------------
# Public API
# ----------------------------
def fetch_mylead_offers(params: Optional[dict] = None) -> List[Dict[str, Any]]:
    """Fetch and normalize offers from the MyLead API.

    Args:
        params: Optional query parameters for the API request.

    Returns:
        List of offer dictionaries with standardized keys. Returns empty list on error.
    """
    token = load_mylead_token()
    if not token:
        # Soft-fail: tests and prod both expect empty list rather than exception.
        return []

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }

    try:
        data = _make_api_request(MYLEAD_API_URL, headers, params)
        if data is None:
            return []
    except Exception as exc:
        logger.error(f"Error fetching MyLead offers: {exc}")
        return []

    raw_offers = _extract_offers(data)
    offers: List[Dict[str, Any]] = []

    for offer in raw_offers:
        try:
            parsed_offer = _parse_offer(offer)
            if _validate_offer(parsed_offer):
                offers.append(parsed_offer)
        except Exception as exc:
            logger.warning(f"Failed to parse a MyLead offer: {exc}")
            continue

    logger.info(f"Successfully fetched {len(offers)} offers from MyLead")
    return offers


# ----------------------------
# HTTP / Parsing helpers
# ----------------------------
def _make_api_request(
    url: str,
    headers: dict,
    params: Optional[dict] = None
) -> Optional[dict | list]:
    """Make API request with retry logic and rate limiting."""
    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(
                url,
                headers=headers,
                params=params,
                timeout=MYLEAD_API_TIMEOUT,
            )
            # If the server returned HTML, it's likely the wrong endpoint
            ctype = response.headers.get("content-type", "")
            if "application/json" not in ctype.lower():
                snippet = (response.text or "")[:300].replace("\n", " ")
                logger.error(
                    f"❌ Unexpected content-type '{ctype}' at {url} "
                    f"(status {response.status_code}). Body: {snippet}"
                )
                response.raise_for_status()

            response.raise_for_status()
            try:
                return response.json()
            except ValueError as je:
                snippet = (response.text or "")[:300].replace("\n", " ")
                logger.error(f"❌ JSON decode failed: {je}. Body: {snippet}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RATE_LIMIT_DELAY * (attempt + 1))
                    continue
                return None

        except requests.exceptions.RequestException as exc:
            logger.warning(f"Attempt {attempt + 1} failed: {exc}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RATE_LIMIT_DELAY * (attempt + 1))
                continue
            raise
    return None


def _extract_offers(data: dict | list) -> List[dict]:
    """Support multiple response shapes from MyLead."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        if isinstance(data.get("data"), list):
            return data["data"]
        if isinstance(data.get("offers"), list):
            return data["offers"]
    # Unknown shape
    logger.error(f"❌ Unexpected MyLead response shape: {type(data).__name__}")
    return []


def _parse_offer(offer: dict) -> Dict[str, Any]:
    """Parse and normalize a single offer from MyLead API response."""
    name = (offer.get("name") or offer.get("title") or "").strip()
    url = (offer.get("tracking_url") or offer.get("url") or "").strip()
    geos = offer.get("geos") or offer.get("countries") or []
    device_raw = offer.get("device") or offer.get("devices")
    category = (offer.get("category") or "").strip()
    allowed_traffic = offer.get("allowed_traffic") or []
    requirements = (offer.get("requirements") or "").strip()

    try:
        payout_val = float(offer.get("payout", 0) or 0)
    except Exception:
        payout_val = 0.0

    parsed_offer = {
        "name": name,
        "network": "MyLead",
        "url": url,
        "geo": list(sorted(set(geos))) if isinstance(geos, list) else [],
        "device": _parse_device(device_raw),
        "payout": payout_val,
        "category": category,
        "allowed_traffic": list(sorted(set(allowed_traffic))) if isinstance(allowed_traffic, list) else [],
        "requirements": requirements,
    }
    parsed_offer["tags"] = _generate_tags(parsed_offer)
    return parsed_offer


def _validate_offer(offer: dict) -> bool:
    """Validate that an offer contains all required fields with valid values."""
    if not offer.get("name") or not offer.get("url"):
        return False
    if not isinstance(offer.get("geo", []), list):
        return False
    try:
        float(offer.get("payout", 0))
    except Exception:
        return False
    return True


def _parse_device(device_val: Any) -> str:
    """Normalize the device field with comprehensive mapping."""
    if not device_val:
        return "All"
    if isinstance(device_val, list):
        # Heuristic: if list contains mobile OS, prefer those; else join.
        low = [str(x).lower().strip() for x in device_val]
        if any(x in ("ios", "iphone", "ipad", "apple") for x in low):
            return "iOS"
        if "android" in low:
            return "Android"
        if "desktop" in low or "pc" in low:
            return "Desktop"
        return ", ".join(sorted(set([x.capitalize() for x in low])))
    s = str(device_val).lower().strip()
    mapping = {
        "mobile": "Android",
        "desktop": "Desktop",
        "tablet": "Android",
        "ios": "iOS",
        "android": "Android",
        "smartphone": "Android",
        "all": "All",
        "any": "All",
    }
    return mapping.get(s, s.capitalize())


def _generate_tags(offer: Dict[str, Any]) -> List[str]:
    """Generate tags based on offer attributes."""
    tags: List[str] = []
    requirements_text = (offer.get("requirements") or "").lower()
    allowed_traffic = [t.lower() for t in offer.get("allowed_traffic", [])]
    device = (offer.get("device") or "").lower()
    category = (offer.get("category") or "").lower()
    payout = offer.get("payout", 0.0) or 0.0

    # Requirement-based tags
    if "no login" in requirements_text:
        tags.append("no-login")
    if "email" in requirements_text:
        tags.append("email-required")
    if "credit card" in requirements_text:
        tags.append("cc-required")

    # Traffic source tags
    traffic_tags = {
        "reddit": "Reddit-safe",
        "facebook": "FB-safe",
        "instagram": "IG-safe",
        "google": "Google-safe",
        "email": "Email-safe",
    }
    for source, tag in traffic_tags.items():
        if source in allowed_traffic:
            tags.append(tag)

    # Device tags
    if "mobile" in device or device in ("android", "ios"):
        tags.append("mobile")
    if device == "desktop":
        tags.append("desktop-only")

    # Payout tags
    try:
        p = float(payout)
        if p >= 5.0:
            tags.append("high-payout")
        elif p <= 1.0:
            tags.append("low-payout")
    except Exception:
        pass

    # Category tags
    category_tags = {
        "giveaway": "giveaway",
        "survey": "survey",
        "pin": "pin-submit",
        "app": "app-install",
    }
    for cat, tag in category_tags.items():
        if cat in category:
            tags.append(tag)

    return sorted(list(set(tags)))  # de-dupe + sort
