"""
Offer Sync Utility
==================

This script copies the filtered offers JSON (`cloudflare_offers.json`) from
the current directory into the `public/data` folder of a sibling
`aiqbrain-landing` repository. It is intended to be run manually when you
want to update the offer feed used by the Cloudflare Worker.

Usage:

```
python sync.py
```
"""

import os
import shutil

from utils.logging import setup_logger


def main() -> None:
    logger = setup_logger('sync')
    source_file = 'cloudflare_offers.json'
    if not os.path.isfile(source_file):
        logger.error(f"Source file {source_file} not found. Run main.py first.")
        return

    current_dir = os.path.dirname(os.path.abspath(__file__))
    landing_repo_path = os.path.join(current_dir, '..', 'aiqbrain-landing')
    dest_path = os.path.join(landing_repo_path, 'public', 'data')
    if not os.path.isdir(landing_repo_path):
        logger.error(
            "aiqbrain-landing repository not found adjacent to aggregator. "
            "Ensure both repositories are checked out side by side."
        )
        return

    try:
        os.makedirs(dest_path, exist_ok=True)
        dest_file = os.path.join(dest_path, source_file)
        shutil.copy2(source_file, dest_file)
        logger.info(f"Copied {source_file} to {dest_file}.")
    except Exception as exc:
        logger.error(f"Failed to copy file: {exc}")


if __name__ == '__main__':
    main()