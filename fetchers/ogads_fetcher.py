"""
OGAds Offer Fetcher
===================

This module uses Playwright to sign into the OGAds platform and scrape
available CPA offers from the programs dashboard. OGAds does not provide a
public API for offers, so headless browser automation is necessary. Credentials
must be supplied via the `OGADS_EMAIL` and `OGADS_PASSWORD` environment
variables. See `.env.example` for details.

Enhancements include:
- Browser stealth configuration to reduce detection
- Pagination support
- Enhanced error handling and debugging
- Session persistence
- More robust element selection
- Additional offer validation
"""

import os
import random
import time
from typing import List, Dict, Any

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

from utils.logging import setup_logger

load_dotenv()
logger = setup_logger(__name__)

OGADS_LOGIN_URL = "https://ogads.com/login"
OGADS_OFFERS_URL = "https://ogads.com/programs"
MAX_PAGES = 3  # Maximum number of pages to scrape
REQUEST_DELAY = (1, 3)  # Random delay range between requests

def fetch_ogads_offers(headless: bool = True) -> List[Dict[str, Any]]:
    """Fetch and normalize offers from OGAds via browser automation.

    Args:
        headless: Whether to run browser in headless mode

    Returns:
        List of offer dictionaries matching the standard schema. Returns empty
        list on error.
    """
    email = os.getenv("OGADS_EMAIL")
    password = os.getenv("OGADS_PASSWORD")
    if not email or not password:
        logger.error(
            "OGAds credentials not found in environment variables. Please set "
            "OGADS_EMAIL and OGADS_PASSWORD in your .env file."
        )
        return []

    offers: List[Dict[str, Any]] = []
    with sync_playwright() as p:
        browser = None
        try:
            # Configure browser with realistic settings
            browser = p.chromium.launch(
                headless=headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox"
                ]
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36",
                viewport={"width": 1280, "height": 1024},
                locale="en-US"
            )
            page = context.new_page()

            # Log into OGAds
            logger.info("Logging into OGAds...")
            page.goto(OGADS_LOGIN_URL, timeout=15000)
            page.fill('input[name="email"]', email)
            time.sleep(random.uniform(*REQUEST_DELAY))
            page.fill('input[name="password"]', password)
            time.sleep(random.uniform(*REQUEST_DELAY))
            page.click('button[type="submit"]')

            # Wait for login to complete
            page.wait_for_selector('.offers-table', timeout=20000)
            page.wait_for_load_state("networkidle")

            # Navigate to offers page
            logger.info("Navigating to OGAds programs page...")
            page.goto(OGADS_OFFERS_URL, timeout=15000)
            page.wait_for_selector('.offer-row', timeout=15000)

            # Parse offers with pagination support
            current_page = 1
            while current_page <= MAX_PAGES:
                logger.info(f"Processing page {current_page}...")
                offer_rows = page.query_selector_all('.offer-row:not(.header-row)')

                for row in offer_rows:
                    try:
                        offer = _parse_offer_row(row)
                        if _validate_offer(offer):
                            offers.append(offer)
                    except Exception as exc:
                        logger.warning(f"Error parsing offer row: {exc}")
                        continue

                # Check for and click next page button if available
                next_button = page.query_selector('a.next-page:not(.disabled)')
                if not next_button or current_page >= MAX_PAGES:
                    break

                logger.info("Moving to next page...")
                next_button.click()
                page.wait_for_selector('.offer-row', timeout=15000)
                time.sleep(random.uniform(*REQUEST_DELAY))
                current_page += 1

            logger.info(f"Successfully parsed {len(offers)} offers from OGAds")

            # Save session state for future runs
            context.storage_state(path="ogads_session.json")

        except Exception as exc:
            logger.error(f"Error fetching OGAds offers: {exc}")
            if os.getenv("DEBUG_SCREENSHOTS"):
                page.screenshot(path=f"debug_ogads_{int(time.time())}.png")
        finally:
            if browser:
                browser.close()

    return offers

def _parse_offer_row(row) -> Dict[str, Any]:
    """Parse individual offer row into standardized dictionary."""
    name = row.query_selector('.offer-name').inner_text().strip()
    payout_text = row.query_selector('.offer-payout').inner_text().strip()
    payout = float(payout_text.replace('$', '').replace(',', '').strip())

    geo_elements = row.query_selector_all('.offer-geo .geo-tag')
    geos = [geo.inner_text().strip() for geo in geo_elements if geo.inner_text().strip()]

    device = row.query_selector('.offer-device').inner_text().strip()
    category = row.query_selector('.offer-category').inner_text().strip()

    url_element = row.query_selector('.offer-link a')
    url = url_element.get_attribute('href') if url_element else None

    restrictions = row.query_selector('.offer-restrictions').inner_text().lower()

    # Generate tags based on offer attributes
    tags = _generate_tags(device, restrictions)

    return {
        'name': name,
        'network': 'OGAds',
        'url': f"https://ogads.com{url}" if url else None,
        'geo': geos,
        'device': device,
        'payout': payout,
        'category': category,
        'tags': tags,
    }

def _validate_offer(offer: Dict[str, Any]) -> bool:
    """Validate that required offer fields exist and are valid."""
    if not offer.get("name") or not offer.get("url"):
        return False

    if not isinstance(offer.get("geo", []), list):
        return False

    if not isinstance(offer.get("payout", 0), (int, float)):
        return False

    return True

def _generate_tags(device: str, restrictions: str) -> List[str]:
    """Generate tags based on device and restrictions."""
    tags = []
    device_lower = device.lower()
    restrictions_lower = restrictions.lower()

    # Device tags
    if "mobile" in device_lower or "android" in device_lower or "ios" in device_lower:
        tags.append("mobile")
    elif "desktop" in device_lower:
        tags.append("desktop-only")

    # Requirement tags
    if "no login" in restrictions_lower:
        tags.append("no-login")
    if "email" in restrictions_lower:
        tags.append("email-required")

    # Traffic source tags
    if "reddit" in restrictions_lower:
        tags.append("Reddit-safe")
    if "facebook" in restrictions_lower:
        tags.append("FB-safe")
    if "instagram" in restrictions_lower:
        tags.append("IG-safe")

    return sorted(list(set(tags)))  # Remove duplicates and sort
