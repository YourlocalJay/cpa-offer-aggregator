"""
Logging Utilities
=================

This module provides a convenience function for configuring a logger with
reasonable defaults. Each module in the project should call
`setup_logger(__name__)` to obtain a module‑specific logger. All loggers
inherit from the root logger so that global logging configuration can be
controlled centrally if needed. By default, logs are emitted to the
console at the INFO level.
"""

import logging
from typing import Optional


def setup_logger(name: Optional[str] = None) -> logging.Logger:
    """Create and configure a logger.

    Args:
        name: Name for the logger. When None, the root logger is configured.

    Returns:
        A logger instance configured to emit INFO level logs to the console with a
        simple, human‑readable format.
    """
    logger = logging.getLogger(name)
    # Avoid adding multiple handlers when this function is called repeatedly
    if not logger.handlers:
        logger.setLevel(logging.INFO)

        handler = logging.StreamHandler()
        handler.setLevel(logging.INFO)
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger