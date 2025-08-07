"""
Offer Filtering
===============

This module provides comprehensive filtering capabilities for CPA offers with:
- Geographic targeting
- Device compatibility checks
- Payout thresholds
- Category matching
- Advanced tag-based filtering
- Custom validation rules

The filtering system supports both inclusive and exclusive filtering patterns
and includes detailed logging for debugging purposes.
"""

from typing import List, Dict, Any, Optional, Set, Callable
from dataclasses import dataclass, field
from utils.logging import setup_logger

logger = setup_logger(__name__)

@dataclass
class FilterCriteria:
    """Container for all filter parameters with validation."""
    geo: str = 'US'
    device: str = 'Android'
    min_payout: float = 1.00
    max_payout: Optional[float] = None
    categories: Optional[Set[str]] = None
    required_tags: Optional[Set[str]] = None
    excluded_tags: Optional[Set[str]] = None
    custom_validators: List[Callable[[Dict[str, Any]], bool]] = field(default_factory=list)

    def __post_init__(self):
        """Normalize and validate filter values."""
        self.geo = self.geo.upper()
        self.device = self.device.capitalize()

        if self.categories:
            self.categories = {c.lower() for c in self.categories}

        if self.required_tags:
            self.required_tags = {t.lower() for t in self.required_tags}

        if self.excluded_tags:
            self.excluded_tags = {t.lower() for t in self.excluded_tags}



def filter_offers(
    offers: List[Dict[str, Any]],
    *,
    geo: str = 'US',
    device: str = 'Android',
    min_payout: float = 1.00,
    max_payout: Optional[float] = None,
    categories: Optional[List[str]] = None,
    required_tags: Optional[List[str]] = None,
    excluded_tags: Optional[List[str]] = None,
    custom_validators: Optional[List[Callable[[Dict[str, Any]], bool]]] = None,
) -> List[Dict[str, Any]]:
    """Advanced filtering of CPA offers with multiple criteria.

    Args:
        offers: List of offer dictionaries to filter
        geo: Target country code (e.g., 'US')
        device: Target device type ('Android', 'iOS', 'Desktop', or 'All')
        min_payout: Minimum payout amount
        max_payout: Maximum payout amount (optional)
        categories: Required categories (optional)
        required_tags: Tags that must be present (optional)
        excluded_tags: Tags that must not be present (optional)
        custom_validators: List of additional validation functions

    Returns:
        Filtered list of offers meeting all criteria
    """
    criteria = FilterCriteria(
        geo=geo,
        device=device,
        min_payout=min_payout,
        max_payout=max_payout,
        categories=set(categories) if categories else {'Mobile Submits', 'Giveaways'},
        required_tags=set(required_tags) if required_tags else {'reddit-safe', 'no-login'},
        excluded_tags=set(excluded_tags) if excluded_tags else None,
        custom_validators=custom_validators if custom_validators else []
    )

    filtered: List[Dict[str, Any]] = []
    for offer in offers:
        try:
            if not _validate_offer(offer, criteria):
                continue
            filtered.append(offer)
        except Exception as exc:
            logger.warning(f"Error filtering offer {offer.get('name')}: {exc}")
            continue

    logger.info(
        f"Filtered {len(filtered)}/{len(offers)} offers | "
        f"GEO: {criteria.geo} | Device: {criteria.device} | "
        f"Payout: ${criteria.min_payout}-{f'${criteria.max_payout}' if criteria.max_payout else '∞'}"
    )
    return filtered


def _validate_offer(offer: Dict[str, Any], criteria: FilterCriteria) -> bool:
    """Check if an offer meets all filter criteria."""
    # GEO validation
    if not _validate_geo(offer.get('geo', []), criteria.geo):
        return False

    # Device validation
    if not _validate_device(offer.get('device', ''), criteria.device):
        return False

    # Payout validation
    payout = float(offer.get('payout', 0) or 0)
    if not _validate_payout(payout, criteria.min_payout, criteria.max_payout):
        return False

    # Category validation
    if criteria.categories and not _validate_category(
        offer.get('category', ''),
        criteria.categories
    ):
        return False

    # Tag validation
    offer_tags = {t.lower() for t in offer.get('tags', [])}
    if not _validate_tags(
        offer_tags,
        criteria.required_tags,
        criteria.excluded_tags
    ):
        return False

    # Custom validation
    for validator in criteria.custom_validators:
        if not validator(offer):
            return False

    return True


def _validate_geo(offer_geos: List[str], target_geo: str) -> bool:
    """Check if offer is available in target GEO."""
    return target_geo in {g.upper() for g in offer_geos}


def _validate_device(offer_device: str, target_device: str) -> bool:
    """Check if offer matches device requirements."""
    if target_device.lower() == 'all':
        return True
    return target_device.lower() in offer_device.lower()


def _validate_payout(
    payout: float,
    min_payout: float,
    max_payout: Optional[float]
) -> bool:
    """Check if payout is within required range."""
    if payout < min_payout:
        return False
    if max_payout is not None and payout > max_payout:
        return False
    return True


def _validate_category(
    offer_category: str,
    required_categories: Set[str]
) -> bool:
    """Check if offer matches any required category."""
    return offer_category.lower() in required_categories


def _validate_tags(
    offer_tags: Set[str],
    required_tags: Optional[Set[str]],
    excluded_tags: Optional[Set[str]]
) -> bool:
    """Validate tags against inclusion/exclusion rules."""
    if required_tags and not required_tags.intersection(offer_tags):
        return False
    if excluded_tags and excluded_tags.intersection(offer_tags):
        return False
    return True


# Example custom validators
def validate_high_converting_offer(offer: Dict[str, Any]) -> bool:
    """Example custom validator for high-converting offers."""
    return offer.get('conversion_rate', 0) > 0.2


def validate_quick_approval_offer(offer: Dict[str, Any]) -> bool:
    """Example custom validator for quick-approval offers."""
    return 'instant-approval' in offer.get('tags', [])
