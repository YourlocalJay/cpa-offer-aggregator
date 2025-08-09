"""URL and offer data validation and normalization utilities."""

from urllib.parse import urlparse
from typing import Union, List, Dict, Optional, Tuple

# Immutable set of blocked hosts for better performance and safety
BLOCKED_HOSTS = frozenset({
    "tracking.com", "www.tracking.com",
    "parkingcrew.net", "sedoparking.com",
    "parklogic.com", "dnparking.com"
})

def is_valid_url(url: str) -> bool:
    """Validate URL format and check against blocked hosts.
    
    Args:
        url: The URL string to validate
        
    Returns:
        bool: True if URL is valid and not blocked, False otherwise
    """
    try:
        parsed = urlparse(url)
        return (
            parsed.scheme == "https"
            and bool(parsed.netloc)
            and parsed.netloc.lower() not in BLOCKED_HOSTS
        )
    except (ValueError, AttributeError):
        return False

def normalize_geo(value: Union[str, List, Tuple, None]) -> List[str]:
    """Normalize geographic targeting values to uppercase strings.
    
    Args:
        value: Input value to normalize (can be str, list, tuple, or None)
        
    Returns:
        List[str]: List of uppercase strings, empty list if input is falsy
    """
    if not value:
        return []

    if isinstance(value, (list, tuple)):
        return [str(x).upper() for x in value if x]

    return [str(value).upper()]

# Predefined device mappings for consistent normalization
DEVICE_MAPPINGS = {
    "ios": "iOS",
    "iphone": "iOS",
    "ipad": "iOS",
    "apple": "iOS",
    "android": "Android",
    "desktop": "Desktop",
    "pc": "Desktop",
    "all": "ALL",
    "any": "ALL",
    "*": "ALL",
}

def normalize_device(value: Union[str, List, Tuple, None]) -> List[str]:
    """Normalize device targeting values to consistent format.
    
    Args:
        value: Input value to normalize (can be str, list, tuple, or None)
        
    Returns:
        List[str]: List of normalized device names
    """
    if not value:
        return []

    devices = value if isinstance(value, (list, tuple)) else [value]
    normalized = []

    for device in devices:
        if not device:
            continue

        lower_device = str(device).lower()
        normalized.append(DEVICE_MAPPINGS.get(lower_device, lower_device.capitalize()))

    return normalized

def normalize_offer(raw: Dict) -> Optional[Dict]:
    """Validate and normalize offer data dictionary.
    
    Args:
        raw: Raw offer data dictionary
        
    Returns:
        Optional[Dict]: Normalized offer dictionary or None if invalid/inactive
    """
    url = (raw.get("url") or "").strip()
    if not is_valid_url(url):
        return None

    try:
        payout = float(raw.get("payout", 0))
    except (ValueError, TypeError):
        payout = 0.0

    offer = {
        "name": raw.get("name") or raw.get("title") or "Untitled",
        "network": raw.get("network") or "Unknown",
        "url": url,
        "geo": normalize_geo(raw.get("geo") or raw.get("countries") or ["ALL"]),
        "device": normalize_device(raw.get("device") or raw.get("devices") or ["ALL"]),
        "payout": payout,
        "active": bool(raw.get("active", True)),
    }

    return offer if offer["active"] else None
