"""Command-line entry point for classification runs."""

from __future__ import annotations

import argparse
import logging
from datetime import UTC, datetime, timedelta

from error_analysis.context import AnalysisContext
from error_analysis.logging_config import configure_logging

log = logging.getLogger(__name__)


def main() -> None:
    """
    Classifies the error reports of a past time window into equivalence classes.

    Intended for backfills over large windows, which are too long-running to perform within an
    MCP tool call.
    """
    # parse the command line
    parser = argparse.ArgumentParser(description="Classifies the error reports of a past time window into equivalence classes.")
    parser.add_argument("--days", type=float, default=30.0, help="the number of past days whose reports are to be classified")
    parser.add_argument("--concurrency", type=int, default=8, help="the number of report detail retrievals to perform concurrently")
    args = parser.parse_args()

    # run the classification
    configure_logging()
    classifier = AnalysisContext.create_default().create_classifier(fetch_concurrency=args.concurrency)
    result = classifier.classify_window(since=datetime.now(UTC) - timedelta(days=args.days))
    log.info(
        "Done: %d reports in window, %d newly classified, %d classes created",
        result.reports_seen,
        result.reports_classified,
        result.classes_created,
    )
