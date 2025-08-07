"""
MyLead Offer Fetcher
====================

This module contains a helper function for querying the MyLead API and
translating the response into a uniform offer dictionary format expected by
the aggregator. MyLead provides a REST API which returns JSON describing
available CPA offers. To use this fetcher, generate an access token with
`fetch_mylead_token()` and set the ``MYLEAD_TOKEN`` environment variable.
"""

import os
import time
from typing import Any, Dict, List, Optional

import requests

from utils.logging import setup_logger
logger = setup_logger(__name__)

# Constants
MYLEAD_API_URL = "https://mylead.global/api/v2/offers"
MYLEAD_API_TIMEOUT = 30  # seconds
MAX_RETRIES = 3
RATE_LIMIT_DELAY = 1  # second between retries


def load_mylead_token() -> str:
    token = os.environ.get("MYLEAD_TOKEN")
    if token:
        return token
    raise RuntimeError(
        "❌ MYLEAD_TOKEN not found. Run fetch_mylead_token() first."
    )


def fetch_mylead_offers(params: Optional[dict] = None) -> List[Dict[str, Any]]:
    """Fetch and normalize offers from the MyLead API.

    Args:
        params: Optional query parameters for the API request

    Returns:
        List of offer dictionaries with standardized keys. Returns empty list
        on error.
    """
    try:
        headers = {
            "Authorization": f"Bearer {load_mylead_token()}",
            "Accept": "application/json",
        }
    except RuntimeError as exc:
        logger.error(str(exc))
        return []

    try:
        data = _make_api_request(MYLEAD_API_URL, headers, params)
        if data is None:
            return []
    except Exception as exc:
        logger.error(f"Error fetching MyLead offers: {exc}")
        return []

    offers: List[Dict[str, Any]] = []
    for offer in data.get("data", []):
        try:
            parsed_offer = _parse_offer(offer)
            if _validate_offer(parsed_offer):
                offers.append(parsed_offer)
        except Exception as exc:
            logger.warning(f"Failed to parse a MyLead offer: {exc}")
            continue

    logger.info(f"Successfully fetched {len(offers)} offers from MyLead")
    return offers


def _make_api_request(
    url: str,
    headers: dict,
    params: Optional[dict] = None
) -> Optional[dict]:
    """Make API request with retry logic and rate limiting."""
    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(
                url,
                headers=headers,
                params=params,
                timeout=MYLEAD_API_TIMEOUT
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as exc:
            logger.warning(f"Attempt {attempt + 1} failed: {exc}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RATE_LIMIT_DELAY * (attempt + 1))
                continue
            raise
    return None


def _parse_offer(offer: dict) -> Dict[str, Any]:
    """Parse and normalize a single offer from MyLead API response."""
    parsed_offer = {
        "name": offer.get("name", "").strip(),
        "network": "MyLead",
        "url": offer.get("tracking_url", "").strip(),
        "geo": list(set(offer.get("geos", []) or [])),  # Remove duplicates
        "device": _parse_device(offer.get("device")),
        "payout": float(offer.get("payout", 0) or 0),
        "category": (offer.get("category") or "").strip(),
        "allowed_traffic": list(set(offer.get("allowed_traffic", []) or [])),
        "requirements": (offer.get("requirements") or "").strip(),
    }
    parsed_offer["tags"] = _generate_tags(parsed_offer)
    return parsed_offer


def _validate_offer(offer: dict) -> bool:
    """Validate that an offer contains all required fields with valid values."""
    if not offer.get("name") or not offer.get("url"):
        return False

    if not isinstance(offer.get("geo", []), list):
        return False

    if not isinstance(offer.get("payout", 0), (int, float)):
        return False

    return True


def _parse_device(device_str: Any) -> str:
    """Normalize the device field with comprehensive mapping."""
    if not device_str:
        return "All"

    device_map = {
        "mobile": "Android",
        "desktop": "Desktop",
        "tablet": "Android",
        "ios": "iOS",
        "android": "Android",
        "smartphone": "Android",
        "all": "All",
        "any": "All"
    }

    device_str = str(device_str).lower().strip()
    return device_map.get(device_str, device_str.capitalize())


def _generate_tags(offer: Dict[str, Any]) -> List[str]:
    """Comprehensive tag generation based on offer attributes."""
    tags: List[str] = []
    requirements_text = (offer.get("requirements") or "").lower()
    allowed_traffic = [t.lower() for t in offer.get("allowed_traffic", [])]
    device = (offer.get("device") or "").lower()
    category = (offer.get("category") or "").lower()
    payout = offer.get("payout", 0)

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
        "email": "Email-safe"
    }

    for source, tag in traffic_tags.items():
        if source in allowed_traffic:
            tags.append(tag)

    # Device tags
    if "mobile" in device or device in ["android", "ios"]:
        tags.append("mobile")
    if device == "desktop":
        tags.append("desktop-only")

    # Payout tags
    if payout >= 5.0:
        tags.append("high-payout")
    elif payout <= 1.0:
        tags.append("low-payout")

    # Category tags
    category_tags = {
        "giveaway": "giveaway",
        "survey": "survey",
        "pin": "pin-submit",
        "app": "app-install"
    }

    for cat, tag in category_tags.items():
        if cat in category:
            tags.append(tag)

    return sorted(list(set(tags)))  # Remove duplicates and sort
