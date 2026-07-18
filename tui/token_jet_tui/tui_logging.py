"""Centralised debug logging for Token-Jet TUI.

Import and call setup_logging() early in startup.  All other modules then just do:
    import logging
    log = logging.getLogger(__name__)
"""

from __future__ import annotations

import logging
import logging.handlers
import os

LOG_PATH = "/tmp/token-jet-debug.log"


def setup_logging() -> None:
    root = logging.getLogger()
    if root.handlers:
        return  # already configured

    root.setLevel(logging.DEBUG)

    fh = logging.FileHandler(LOG_PATH, mode="a")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)-8s %(name)s:%(lineno)d  %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    root.addHandler(fh)

    # Keep asyncio noise at WARNING only
    logging.getLogger("asyncio").setLevel(logging.WARNING)
