"""
CPA Offer Aggregator CLI
========================

Enhanced version with:
- Parallel offer fetching
- Better error handling and retries
- More output options
- Progress tracking
- Configuration file support
- Extended logging
"""

import argparse
import json
import os
import shutil
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Tuple

import pandas as pd
from dotenv import load_dotenv

from fetchers.mylead_fetcher import fetch_mylead_offers
from fetchers.ogads_fetcher import fetch_ogads_offers
from fetchers.cpagrip_fetcher import fetch_cpagrip_offers
from filters import filter_offers
from utils.logging import setup_logger
from get_mylead_token import fetch_mylead_token

# Constants
DEFAULT_OUTPUT_DIR = Path("output")
MAX_RETRIES = 3
FETCH_TIMEOUT = 300  # 5 minutes
CONFIG_FILE = "config.json"

def load_config() -> dict:
    """Load configuration from JSON file if it exists."""
    if Path(CONFIG_FILE).exists():
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Warning: Could not load config file - {e}")
    return {}

def save_config(config: dict) -> None:
    """Save configuration to JSON file."""
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)
    except Exception as e:
        print(f"Warning: Could not save config file - {e}")

def fetch_all_offers_parallel(logger=None) -> Tuple[List[Dict[str, Any]], List[Exception]]:
    """Fetch offers from all networks with limited parallelism and retries.

    Playwright-based fetchers are serialized to avoid thread-safety issues,
    while the MyLead API fetcher still runs in a background thread.
    """

    all_offers = []
    errors = []

    def fetch_with_retries(fetcher, network_name):
        for attempt in range(MAX_RETRIES):
            try:
                if logger:
                    logger.info(f"Fetching {network_name} offers (attempt {attempt + 1})...")
                offers = fetcher()
                return offers
            except Exception as e:
                if logger:
                    logger.warning(f"Attempt {attempt + 1} failed for {network_name}: {e}")
                if attempt == MAX_RETRIES - 1:
                    errors.append(f"Failed to fetch {network_name} offers after {MAX_RETRIES} attempts")
                time.sleep(2 ** attempt)  # Exponential backoff
        return []

    # Run the MyLead API fetcher in parallel, but serialize Playwright fetchers.
    with ThreadPoolExecutor(max_workers=1) as executor:
        mylead_future = executor.submit(
            fetch_with_retries, fetch_mylead_offers, "MyLead"
        )

        # Playwright-backed fetchers must not run concurrently. Executing them
        # sequentially prevents race conditions when Playwright manages browser
        # instances in the same process.
        for name, fetcher in [
            ("OGAds", fetch_ogads_offers),
            ("CPAGrip", fetch_cpagrip_offers),
        ]:
            all_offers.extend(fetch_with_retries(fetcher, name))

        all_offers.extend(mylead_future.result())

    return all_offers, errors

def save_to_files(
    all_offers: List[Dict[str, Any]],
    filtered_offers: List[Dict[str, Any]],
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    *,
    logger=None,
) -> None:
    """Persist the offer lists to JSON and CSV files with timestamp."""
    try:
        output_dir.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Save all offers
        all_offers_path = output_dir / f"offers_all_{timestamp}.json"
        with open(all_offers_path, 'w', encoding='utf-8') as f:
            json.dump(all_offers, f, indent=2)

        # Save filtered offers
        filtered_path = output_dir / f"offers_filtered_{timestamp}.json"
        with open(filtered_path, 'w', encoding='utf-8') as f:
            json.dump(filtered_offers, f, indent=2)

        # Save to CSV
        csv_path = output_dir / f"offers_{timestamp}.csv"
        df = pd.DataFrame(all_offers)
        df.to_csv(csv_path, index=False)

        # Save latest files without timestamp
        for src, dest in [
            (all_offers_path, output_dir / "offers_all_latest.json"),
            (filtered_path, output_dir / "offers_filtered_latest.json"),
            (csv_path, output_dir / "offers_latest.csv")
        ]:
            shutil.copy2(src, dest)

        if logger:
            logger.info(f"Saved {len(all_offers)} offers to {all_offers_path}")
            logger.info(f"Saved {len(filtered_offers)} filtered offers to {filtered_path}")
            logger.info(f"Saved CSV report to {csv_path}")

    except Exception as exc:
        if logger:
            logger.error(f"Error saving offer files: {exc}")
        raise

def sync_to_destination(
    source_path: Path,
    destinations: List[Dict[str, str]],
    logger=None
) -> None:
    """Sync files to multiple destinations."""
    for dest in destinations:
        try:
            dest_path = Path(dest["path"])
            if dest.get("enabled", True):
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_path, dest_path)
                if logger:
                    logger.info(f"Copied to {dest_path}")
        except Exception as e:
            if logger:
                logger.error(f"Failed to sync to {dest.get('path')}: {e}")

def display_offers(offers: List[Dict[str, Any]], max_display: int = 20) -> None:
    """Display offers in a readable format."""
    print(f"\n=== Displaying {min(len(offers), max_display)} of {len(offers)} filtered offers ===")
    for i, offer in enumerate(offers[:max_display], 1):
        print(f"\n{i}. {offer['name']} ({offer['network']})")
        print(f"   Payout: ${offer['payout']:.2f}")
        print(f"   GEO: {', '.join(offer['geo'])}")
        print(f"   Device: {offer['device']}")
        print(f"   Category: {offer.get('category', 'N/A')}")
        print(f"   Tags: {', '.join(offer.get('tags', []))}")
        print(f"   URL: {offer['url'][:80]}{'...' if len(offer['url']) > 80 else ''}")

def main() -> None:
    """Enhanced main entry point for the CPA Offer Aggregator CLI."""
    # Load config and environment variables
    config = load_config()
    load_dotenv()

    # Set up argument parser with config defaults
    parser = argparse.ArgumentParser(description='CPA Offer Aggregator')
    parser.add_argument(
        '--geo',
        default=config.get('geo', 'US'),
        help='Target GEO (e.g., US, CA)'
    )
    parser.add_argument(
        '--device',
        choices=['Android', 'iOS', 'Desktop', 'All'],
        default=config.get('device', 'Android'),
        help='Target device type',
    )
    parser.add_argument(
        '--min-payout',
        type=float,
        default=config.get('min_payout', 1.00),
        help='Minimum payout threshold',
    )
    parser.add_argument(
        '--max-payout',
        type=float,
        default=config.get('max_payout'),
        help='Maximum payout threshold (optional)',
    )
    parser.add_argument(
        '--categories',
        nargs='+',
        default=config.get('categories', ['Mobile Submits', 'Giveaways']),
        help='Preferred offer categories (space separated)',
    )
    parser.add_argument(
        '--required-tags',
        nargs='+',
        default=config.get('required_tags', ['Reddit-safe', 'no-login']),
        help='Required tags (space separated)',
    )
    parser.add_argument(
        '--excluded-tags',
        nargs='+',
        default=config.get('excluded_tags'),
        help='Excluded tags (space separated)',
    )
    parser.add_argument(
        '--output-dir',
        default=config.get('output_dir', 'output'),
        help='Output directory for files',
    )
    parser.add_argument(
        '--max-display',
        type=int,
        default=20,
        help='Maximum number of offers to display',
    )
    parser.add_argument(
        '--sync',
        action='store_true',
        help='Sync filtered offers to configured destinations',
    )
    parser.add_argument(
        '--save-config',
        action='store_true',
        help='Save current arguments as new default configuration',
    )
    args = parser.parse_args()

    # Save config if requested
    if args.save_config:
        new_config = {
            'geo': args.geo,
            'device': args.device,
            'min_payout': args.min_payout,
            'max_payout': args.max_payout,
            'categories': args.categories,
            'required_tags': args.required_tags,
            'excluded_tags': args.excluded_tags,
            'output_dir': args.output_dir,
        }
        save_config(new_config)
        print("Configuration saved.")

    # Set up logging
    logger = setup_logger('cpa_offer_aggregator')
    logger.info(
        f"Starting CPA Offer Aggregator with filters:\n"
        f"  GEO: {args.geo}\n"
        f"  Device: {args.device}\n"
        f"  Payout: ${args.min_payout}" +
        (f"-${args.max_payout}" if args.max_payout else "+") + "\n"
        f"  Categories: {args.categories}\n"
        f"  Required Tags: {args.required_tags}\n" +
        (f"  Excluded Tags: {args.excluded_tags}\n" if args.excluded_tags else "")
    )

    # Generate token before fetching offers
    token = fetch_mylead_token()
    if token:
        os.environ["MYLEAD_TOKEN"] = token
    else:
        logger.warning("MyLead token not retrieved; MyLead offers may be unavailable.")

    # Fetch offers from all networks in parallel
    start_time = time.time()
    all_offers, errors = fetch_all_offers_parallel(logger)
    fetch_duration = time.time() - start_time

    for error in errors:
        logger.error(error)

    logger.info(
        f"Fetched {len(all_offers)} offers in {fetch_duration:.2f} seconds "
        f"({len(errors)} networks failed)"
    )

    # Filter offers
    filtered_offers = filter_offers(
        all_offers,
        geo=args.geo,
        device=args.device,
        min_payout=args.min_payout,
        max_payout=args.max_payout,
        categories=args.categories,
        required_tags=args.required_tags,
        excluded_tags=args.excluded_tags,
    )
    logger.info(f"Filtered to {len(filtered_offers)} offers")

    # Save results
    output_dir = Path(args.output_dir)
    try:
        save_to_files(
            all_offers,
            filtered_offers,
            output_dir=output_dir,
            logger=logger,
        )
    except Exception as e:
        logger.error(f"Failed to save files: {e}")
        return

    # Sync to destinations if requested
    if args.sync and config.get('destinations'):
        logger.info("Syncing to configured destinations...")
        sync_to_destination(
            output_dir / "offers_filtered_latest.json",
            config['destinations'],
            logger=logger
        )

    # Display results
    display_offers(filtered_offers, max_display=args.max_display)

    # Print summary
    print("\n=== Summary ===")
    print(f"Total offers fetched: {len(all_offers)}")
    print(f"Offers after filtering: {len(filtered_offers)}")
    print(f"Output files saved to: {output_dir.absolute()}")
    if errors:
        print(f"\nWarnings: {len(errors)} networks failed to fetch")

if __name__ == '__main__':
    main()
