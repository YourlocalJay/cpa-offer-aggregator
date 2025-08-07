"""
CPAGrip Offer Fetcher
=====================

This module uses Playwright to sign into CPAGrip and scrape available offers
from the affiliate dashboard. Since CPAGrip does not expose a public API,
browser automation is used to gather offer data. You must provide your
CPAGrip username and password via the `CPAGRIP_USERNAME` and
`CPAGRIP_PASSWORD` environment variables. See `.env.example` for details.

Note that web scraping of affiliate networks may violate their terms of
service. Use at your own discretion.
"""

import os
import random
import time
from typing import List, Dict, Any, Optional

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

from utils.logging import setup_logger

load_dotenv()
logger = setup_logger(__name__)

CPAGRIP_LOGIN_URL = "https://www.cpagrip.com/login.php"
CPAGRIP_OFFERS_URL = "https://www.cpagrip.com/showoffers.php"


def _validate_offer(offer: Dict[str, Any]) -> bool:
    """Validate that an offer contains all required fields with valid values."""
    required_fields = ['name', 'url', 'geo', 'payout']
    return all(field in offer and offer[field] for field in required_fields)


def _parse_payout(payout_text: str) -> Optional[float]:
    """Safely parse payout text into a float value."""
    try:
        return float(
            payout_text.replace('$', '')
                      .replace(',', '')
                      .strip()
        )
    except (ValueError, AttributeError):
        return None


def fetch_cpagrip_offers(
    max_pages: int = 3,
    headless: bool = True
) -> List[Dict[str, Any]]:
    """Fetch and normalize offers from CPAGrip via browser automation.

    Args:
        max_pages: Maximum number of offer pages to scrape
        headless: Whether to run browser in headless mode

    Returns:
        List of offer dictionaries matching the standard schema. Returns empty
        list on error.
    """
    username = os.getenv("CPAGRIP_USERNAME")
    password = os.getenv("CPAGRIP_PASSWORD")
    if not username or not password:
        logger.error(
            "CPAGrip credentials not found in environment variables. Please set "
            "CPAGRIP_USERNAME and CPAGRIP_PASSWORD in your .env file."
        )
        return []

    offers: List[Dict[str, Any]] = []
    with sync_playwright() as p:
        browser = None
        try:
            browser = p.chromium.launch(
                headless=headless,
                args=["--no-sandbox"]
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) ...",
                viewport={"width": 1280, "height": 1024}
            )
            page = context.new_page()

            # Log into CPAGrip
            logger.info("Logging into CPAGrip...")
            page.goto(CPAGRIP_LOGIN_URL, timeout=15000)
            page.wait_for_selector('input[name="username"]', state="visible")
            page.fill('input[name="username"]', username)
            time.sleep(random.uniform(0.5, 1.5))
            page.fill('input[name="password"]', password)
            time.sleep(random.uniform(0.5, 1.5))
            page.click('input[name="submit"]')
            page.wait_for_selector('#offer_table', timeout=15000)
            page.wait_for_load_state('networkidle')

            # Navigate to offers page
            logger.info("Navigating to CPAGrip offers page...")
            page.goto(CPAGRIP_OFFERS_URL, timeout=15000)
            page.wait_for_selector('#offer_table tr.offer_row', timeout=10000)

            # Parse offers with pagination
            current_page = 1
            while current_page <= max_pages:
                logger.info(f"Parsing page {current_page}...")
                offer_rows = page.query_selector_all('#offer_table tr.offer_row')

                for row in offer_rows:
                    try:
                        name = row.query_selector('.offer_name').inner_text().strip()
                        payout_text = row.query_selector('.offer_payout').inner_text()
                        payout = _parse_payout(payout_text)
                        if payout is None:
                            continue

                        geo_elements = row.query_selector_all('.offer_geo img')
                        geos = []
                        for geo in geo_elements:
                            try:
                                title = geo.get_attribute('title')
                                if title and title not in geos:
                                    geos.append(title)
                            except Exception:
                                continue

                        device = row.query_selector('.offer_device').inner_text().strip()
                        category = row.query_selector('.offer_category').inner_text().strip()
                        url_element = row.query_selector('.offer_link a')
                        url = url_element.get_attribute('href') if url_element else None

                        if not url:
                            continue

                        # Determine tags
                        restrictions = row.query_selector('.offer_restrictions').inner_text().lower()
                        tags: List[str] = []
                        if 'no login' in restrictions:
                            tags.append('no-login')
                        if 'reddit' in restrictions:
                            tags.append('Reddit-safe')
                        if 'mobile' in device.lower():
                            tags.append('mobile')

                        offer = {
                            'name': name,
                            'network': 'CPAGrip',
                            'url': f"https://www.cpagrip.com{url}",
                            'geo': geos,
                            'device': device,
                            'payout': payout,
                            'category': category,
                            'tags': tags,
                        }

                        if _validate_offer(offer):
                            offers.append(offer)
                        else:
                            logger.warning(f"Skipping invalid offer: {name}")

                    except Exception as exc:
                        logger.warning(f"Error parsing offer row: {exc}")
                        continue

                # Check for next page
                next_button = page.query_selector('a.next_page:not(.disabled)')
                if not next_button or current_page >= max_pages:
                    break

                logger.info("Moving to next page...")
                next_button.click()
                page.wait_for_selector('#offer_table tr.offer_row', timeout=10000)
                time.sleep(random.uniform(1, 3))
                current_page += 1

            logger.info(f"Successfully parsed {len(offers)} offers from CPAGrip")

            # Save session for future runs
            context.storage_state(path="cpagrip_session.json")

        except Exception as exc:
            logger.error(f"Error fetching CPAGrip offers: {exc}")
            if os.getenv('DEBUG_SCREENSHOTS'):
                page.screenshot(path=f"debug_cpagrip_{int(time.time())}.png")
        finally:
            if browser:
                browser.close()

    return offers
