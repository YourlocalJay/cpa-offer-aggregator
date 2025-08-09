"""
CPAGrip Offer Fetcher (hardened)
--------------------------------
- Verifies login success before scraping
- Detects Cloudflare/captcha interstitials
- Uses safe selector access everywhere
- Builds offer URLs robustly (no double-prepend)
- GEO fallbacks when flag images are absent
"""

from __future__ import annotations

import os
import random
import time
from typing import List, Dict, Any, Optional

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, Page, Browser, TimeoutError as PWTimeoutError

from utils.logging import setup_logger

load_dotenv()
logger = setup_logger(__name__)

CPAGRIP_BASE = "https://www.cpagrip.com"
CPAGRIP_LOGIN_URL = f"{CPAGRIP_BASE}/login.php"
CPAGRIP_OFFERS_URL = f"{CPAGRIP_BASE}/showoffers.php"


# ----------------------------
# Helpers
# ----------------------------
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


def _parse_payout(payout_text: str) -> Optional[float]:
    try:
        return float(payout_text.replace("$", "").replace(",", "").strip())
    except Exception:
        return None


def _validate_offer(offer: Dict[str, Any]) -> bool:
    req = ("name", "url", "geo", "payout")
    if not all(k in offer for k in req):
        return False
    if not offer["name"] or not offer["url"]:
        return False
    if not isinstance(offer["geo"], list):
        return False
    try:
        float(offer["payout"])
    except Exception:
        return False
    return True


def _looks_like_cloudflare(page: Page) -> bool:
    txt = ""
    try:
        txt = page.text_content("body") or ""
    except Exception:
        pass

    if "Just a moment..." in txt or "cf-chl" in txt or "Cloudflare" in txt:
        return True

    # Common challenge selectors
    for sel in ("#challenge-form", "#cf-chl-widget", 'form[action*="challenge"]'):
        try:
            if page.query_selector(sel):
                return True
        except Exception:
            continue
    return False


def _join_url(base: str, href: str) -> str:
    if not href:
        return ""
    h = href.strip()
    if h.startswith("http://") or h.startswith("https://"):
        return h
    if h.startswith("/"):
        return f"{base}{h}"
    return f"{base}/{h.lstrip('/')}"


# ----------------------------
# Main fetcher
# ----------------------------
def fetch_cpagrip_offers(
    max_pages: int = 3,
    headless: bool = True,
    slow_mode: bool = False,
) -> List[Dict[str, Any]]:
    """
    Scrape CPAGrip offers via Playwright.
    Returns [] on any blocking issue (bad creds, captcha, DOM break).
    """
    username = os.getenv("CPAGRIP_USERNAME")
    password = os.getenv("CPAGRIP_PASSWORD")
    if not username or not password:
        logger.error(
            "CPAGrip credentials not found. Set CPAGRIP_USERNAME and CPAGRIP_PASSWORD in .env"
        )
        return []

    offers: List[Dict[str, Any]] = []
    with sync_playwright() as p:
        browser: Optional[Browser] = None
        page: Optional[Page] = None
        try:
            browser = p.chromium.launch(
                headless=headless,
                args=["--no-sandbox"],
                slow_mo=250 if slow_mode else 0,
            )
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1360, "height": 900},
            )
            page = context.new_page()

            # --- Login ---
            logger.info("Logging into CPAGrip…")
            page.goto(CPAGRIP_LOGIN_URL, timeout=20000)
            if _looks_like_cloudflare(page):
                logger.error("Blocked by Cloudflare before login.")
                return []

            page.wait_for_selector('input[name="username"]', timeout=15000)
            page.fill('input[name="username"]', username)
            time.sleep(random.uniform(0.4, 1.1))
            page.fill('input[name="password"]', password)
            time.sleep(random.uniform(0.4, 1.1))
            page.click('input[type="submit"], input[name="submit"]')

            # Wait for either offers link or stay-on-login signal
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except PWTimeoutError:
                pass

            if _looks_like_cloudflare(page):
                logger.error("Blocked by Cloudflare after login submit.")
                return []

            # Heuristic: if login failed, we’ll still be on login page with username field visible
            still_on_login = False
            try:
                page.wait_for_selector('input[name="username"]', timeout=4000)
                still_on_login = True
            except PWTimeoutError:
                still_on_login = False

            if still_on_login:
                logger.error("Login failed — still on login form.")
                return []

            # Navigate explicitly to offers page (even if redirected)
            logger.info("Navigating to CPAGrip offers page…")
            page.goto(CPAGRIP_OFFERS_URL, timeout=20000)
            if _looks_like_cloudflare(page):
                logger.error("Blocked by Cloudflare on offers page.")
                return []

            # Ensure table exists
            try:
                page.wait_for_selector("#offer_table", timeout=15000)
            except PWTimeoutError:
                logger.error("Offer table not found — DOM might have changed.")
                return []

            # -------------------
            # Pagination + parse
            # -------------------
            current_page = 1
            while current_page <= max_pages:
                logger.info(f"Parsing offers (page {current_page}/{max_pages})…")

                try:
                    page.wait_for_selector("#offer_table tr.offer_row", timeout=10000)
                except PWTimeoutError:
                    logger.warning("No rows found on this page; stopping.")
                    break

                rows = page.query_selector_all("#offer_table tr.offer_row")
                for row in rows:
                    try:
                        name_el = row.query_selector(".offer_name")
                        payout_el = row.query_selector(".offer_payout")
                        device_el = row.query_selector(".offer_device")
                        category_el = row.query_selector(".offer_category")
                        restrictions_el = row.query_selector(".offer_restrictions")
                        url_el = row.query_selector(".offer_link a")

                        name = _safe_text(name_el)
                        payout = _parse_payout(_safe_text(payout_el))
                        device = _safe_text(device_el)
                        category = _safe_text(category_el)
                        restrictions = _safe_text(restrictions_el).lower()
                        href = _safe_attr(url_el, "href") or ""

                        if not name or payout is None or not href:
                            continue

                        # GEO via flag <img title="US">, fallback to container text
                        geos: List[str] = []
                        try:
                            imgs = row.query_selector_all(".offer_geo img")
                            for img in imgs:
                                title = _safe_attr(img, "title")
                                if title and title not in geos:
                                    geos.append(title)
                        except Exception:
                            pass
                        if not geos:
                            geo_text_el = row.query_selector(".offer_geo")
                            geo_text = _safe_text(geo_text_el)
                            if geo_text:
                                # crude split; adjust if UI changes
                                for token in geo_text.replace(",", " ").split():
                                    t = token.strip().upper()
                                    if t and t.isalpha() and 2 <= len(t) <= 3:
                                        if t not in geos:
                                            geos.append(t)

                        # Tags
                        tags: List[str] = []
                        if "no login" in restrictions:
                            tags.append("no-login")
                        if "reddit" in restrictions:
                            tags.append("Reddit-safe")
                        if "mobile" in device.lower():
                            tags.append("mobile")

                        url = _join_url(CPAGRIP_BASE, href)

                        offer = {
                            "name": name,
                            "network": "CPAGrip",
                            "url": url,
                            "geo": geos or ["ALL"],
                            "device": device or "ALL",
                            "payout": float(payout),
                            "category": category,
                            "tags": tags,
                            "active": True,
                        }

                        if _validate_offer(offer):
                            offers.append(offer)
                        else:
                            logger.warning(f"Skipping invalid offer: {name}")

                    except Exception as e:
                        logger.warning(f"Error parsing row: {e}")
                        continue

                # Next page?
                next_btn = page.query_selector("a.next_page:not(.disabled)")
                if not next_btn or current_page >= max_pages:
                    break

                logger.info("Moving to next page…")
                next_btn.click()
                try:
                    page.wait_for_load_state("networkidle", timeout=15000)
                except PWTimeoutError:
                    pass
                time.sleep(random.uniform(0.8, 1.6))
                current_page += 1

            logger.info(f"Done — parsed {len(offers)} CPAGrip offers.")
            # Save session for reuse (defeats login/captcha in some cases)
            try:
                context.storage_state(path="cpagrip_session.json")
            except Exception:
                pass

        except Exception as exc:
            logger.error(f"Error fetching CPAGrip offers: {exc}")
            try:
                if page and os.getenv("DEBUG_SCREENSHOTS"):
                    page.screenshot(path=f"debug_cpagrip_{int(time.time())}.png")
            except Exception:
                pass
        finally:
            if browser:
                browser.close()

    return offers
