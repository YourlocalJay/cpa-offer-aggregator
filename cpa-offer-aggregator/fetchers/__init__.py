"""Helper package exposing fetch functions for each supported network.

This package provides a unified interface for fetching CPA offers from
different networks. Each module within this package should define a
`fetch_*_offers` function that returns a list of offer dictionaries. See
`mylead_fetcher.py` for a reference implementation.
"""