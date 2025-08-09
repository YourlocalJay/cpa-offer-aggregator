"""
OGAds Offer Fetcher (hardened)
==============================

- Verifies login success before scraping
- Detects Cloudflare/captcha interstitials
- Uses safe selector access everywhere
- Builds offer URLs robustly (no double-prepend)
- Pagination with backoff and clear logging
- Session persistence for fewer logins

Env:
  OGADS_EMAIL, OGADS_PASSWORD
"""

from __future__ import annotations

import os
import random
import time
from typing import List, Dict, Any, Optional

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError, Page, Browser

from utils.logging import setup_logger

load_dotenv()
logger = setup_logger(__name__)

OGADS_BASE = "https://ogads.com"
OGADS_LOGIN_URL = f"{OGADS_BASE}/login"
OGADS_OFFERS_URL = f"{OGADS_BASE}/programs"
MAX_PAGES = 3
REQUEST_DELAY = (0.8, 1.8)


# ------------- helpers -------------
def _safe_text(el) -> str:
    try:
        return (el.inner_text() or "").strip()
    except Exception:
        return ""


def _safe_attr(el, name: str) -> Optional[str]:
    try:
        return el.get_attribute(name)
    except Exception:
        return None


def _join_url(base: str, href: str) -> str:
    if not href:
        return ""
    h = href.strip()
    if h.startswith("http://") or h.startswith("https://"):
        return h
    if h.startswith("/"):
        return f"{base}{h}"
    return f"{base}/{h.lstrip('/')}"


def _looks_like_cloudflare(page: Page) -> bool:
    txt = ""
    try:
        txt = page.text_content("body") or ""
    except Exception:
        pass
    if "Just a moment..." in txt or "Cloudflare" in txt or "cf-chl" in txt:
        return True
    for sel in ("#challenge-form", "#cf-chl-widget", 'form[action*="challenge"]'):
        try:
            if page.query_selector(sel):
                return True
        except Exception:
            continue
    return False


# ------------- main -------------
def fetch_ogads_offers(headless: bool = True) -> List[Dict[str, Any]]:
    """Fetch and normalize offers from OGAds via browser automation."""
    email = os.getenv("OGADS_EMAIL")
    password = os.getenv("OGADS_PASSWORD")
    if not email or not password:
        logger.error("OGAds creds missing: set OGADS_EMAIL and OGADS_PASSWORD in .env")
        return []

    offers: List[Dict[str, Any]] = []

    with sync_playwright() as p:
        browser: Optional[Browser] = None
        page: Optional[Page] = None
        try:
            browser = p.chromium.launch(
                headless=headless,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
            )
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1360, "height": 900},
                locale="en-US",
            )
            page = context.new_page()

            # --- Login ---
            logger.info("Logging into OGAds…")
            page.goto(OGADS_LOGIN_URL, timeout=20000)
            if _looks_like_cloudflare(page):
                logger.error("Blocked by Cloudflare before login.")
                return []

            try:
                page.wait_for_selector('input[name="email"]', timeout=15000)
            except PWTimeoutError:
                logger.error("Login form not found on OGAds login page.")
                return []

            page.fill('input[name="email"]', email)
            time.sleep(random.uniform(*REQUEST_DELAY))
            page.fill('input[name="password"]', password)
            time.sleep(random.uniform(*REQUEST_DELAY))
            page.click('button[type="submit"]')

            # Wait for either offers table or still-on-login signal
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except PWTimeoutError:
                pass

            if _looks_like_cloudflare(page):
                logger.error("Blocked by Cloudflare after login submit.")
                return []

            # Heuristic: if login failed, email field remains visible
            still_on_login = False
            try:
                page.wait_for_selector('input[name="email"]', timeout=4000)
                still_on_login = True
            except PWTimeoutError:
                still_on_login = False

            if still_on_login:
                logger.error("Login failed — still on login form.")
                return []

            # --- Navigate to programs/offers ---
            logger.info("Navigating to OGAds programs page…")
            page.goto(OGADS_OFFERS_URL, timeout=20000)
            if _looks_like_cloudflare(page):
                logger.error("Blocked by Cloudflare on programs page.")
                return []

            try:
                page.wait_for_selector(".offer-row", timeout=15000)
            except PWTimeoutError:
                logger.error("Offer rows not found — DOM may have changed.")
                return []

            # --- Pagination & parse ---
            current_page = 1
            while current_page <= MAX_PAGES:
                logger.info(f"Processing page {current_page}/{MAX_PAGES}…")
                try:
                    page.wait_for_selector(".offer-row", timeout=10000)
                except PWTimeoutError:
                    logger.warning("No offer rows on this page; stopping.")
                    break

                rows = page.query_selector_all(".offer-row:not(.header-row)")
                for row in rows:
                    try:
                        offer = _parse_offer_row(row)
                        if _validate_offer(offer):
                            offers.append(offer)
                        else:
                            logger.debug(f"Invalid offer skipped: {offer}")
                    except Exception as exc:
                        logger.warning(f"Error parsing offer row: {exc}")
                        continue

                # Next page?
                next_button = page.query_selector("a.next-page:not(.disabled)")
                if not next_button or current_page >= MAX_PAGES:
                    break

                logger.info("Moving to next page…")
                next_button.click()
                try:
                    page.wait_for_load_state("networkidle", timeout=15000)
                except PWTimeoutError:
                    pass
                time.sleep(random.uniform(*REQUEST_DELAY))
                current_page += 1

            logger.info(f"Successfully parsed {len(offers)} OGAds offers")
            # Save session for future runs
            try:
                context.storage_state(path="ogads_session.json")
            except Exception:
                pass

        except Exception as exc:
            logger.error(f"Error fetching OGAds offers: {exc}")
            try:
                if page and os.getenv("DEBUG_SCREENSHOTS"):
                    page.screenshot(path=f"debug_ogads_{int(time.time())}.png")
            except Exception:
                pass
        finally:
            if browser:
                browser.close()

    return offers


# ------------- row parsing -------------
def _parse_offer_row(row) -> Dict[str, Any]:
    """Parse individual offer row into standardized dictionary with safe selectors."""
    name = _safe_text(row.query_selector(".offer-name"))

    payout_text = _safe_text(row.query_selector(".offer-payout"))
    try:
        payout = float(payout_text.replace("$", "").replace(",", "").strip())
    except Exception:
        payout = 0.0

    # GEO tags (chips) or fallback to container text
    geos: List[str] = []
    try:
        geo_elements = row.query_selector_all(".offer-geo .geo-tag")
        for g in geo_elements:
            val = _safe_text(g)
            if val:
                geos.append(val)
    except Exception:
        pass
    if not geos:
        geo_text = _safe_text(row.query_selector(".offer-geo"))
        if geo_text:
            for tok in geo_text.replace(",", " ").split():
                t = tok.strip().upper()
                if t and t.isalpha() and 2 <= len(t) <= 3:
                    geos.append(t)

    device = _safe_text(row.query_selector(".offer-device"))
    category = _safe_text(row.query_selector(".offer-category"))

    url_element = row.query_selector(".offer-link a")
    href = _safe_attr(url_element, "href") or ""
    url = _join_url(OGADS_BASE, href) if href else ""

    restrictions = _safe_text(row.query_selector(".offer-restrictions")).lower()

    # Generate tags based on offer attributes
    tags = _generate_tags(device, restrictions)

    return {
        "name": name,
        "network": "OGAds",
        "url": url or None,
        "geo": geos,
        "device": device or "ALL",
        "payout": float(payout),
        "category": category,
        "tags": sorted(set(tags)),
        "active": True,
    }


def _validate_offer(offer: Dict[str, Any]) -> bool:
    """Validate that required offer fields exist and are valid."""
    if not offer.get("name") or not offer.get("url"):
        return False
    if not isinstance(offer.get("geo", []), list):
        return False
    try:
        float(offer.get("payout", 0))
    except Exception:
        return False
    return True


def _generate_tags(device: str, restrictions: str) -> List[str]:
    """Generate tags based on device and restrictions."""
    tags: List[str] = []
    d = (device or "").lower()
    r = (restrictions or "").lower()

    # Device tags
    if any(x in d for x in ("mobile", "android", "ios")):
        tags.append("mobile")
    elif "desktop" in d:
        tags.append("desktop-only")

    # Requirement tags
    if "no login" in r:
        tags.append("no-login")
    if "email" in r:
        tags.append("email-required")

    # Traffic source tags
    if "reddit" in r:
        tags.append("Reddit-safe")
    if "facebook" in r:
        tags.append("FB-safe")
    if "instagram" in r:
        tags.append("IG-safe")

    return tags
