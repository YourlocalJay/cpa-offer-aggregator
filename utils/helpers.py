"""
Helper Functions
================

This module can house miscellaneous helper functions for the aggregator.
Currently it defines a placeholder function and can be extended with
parsing utilities, data transformation helpers or other common code.
"""

from __future__ import annotations

from typing import Any


def noop(value: Any) -> Any:
    """Return the input unchanged.

    This is a placeholder function to illustrate the structure of the helpers
    module. Remove or replace this function with real helpers as needed.
    """
    return value