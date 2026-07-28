"""Logging configuration for the platform's entry points."""

from __future__ import annotations

import logging
import sys
from typing import TextIO


def configure_logging(level: int = logging.INFO, stream: TextIO | None = None) -> None:
    """
    Configures root logging for a platform entry point.

    Per-request log messages of the HTTP client (httpx) are demoted to debug visibility: they are
    shown only when the root level is ``DEBUG``.

    :param level: the root log level
    :param stream: the stream to log to; standard error if ``None``
    """
    logging.basicConfig(
        level=level,
        stream=stream if stream is not None else sys.stderr,
        format="%(levelname)-5s %(asctime)-15s [%(threadName)s] %(name)s:%(funcName)s:%(lineno)d - %(message)s",
    )
    if level > logging.DEBUG:
        logging.getLogger("httpx").setLevel(logging.WARNING)
