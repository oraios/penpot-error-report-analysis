"""The workflow associating error reports with equivalence classes."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from error_analysis.fingerprint.algorithm import FingerprintAlgorithm
from error_analysis.persistence.repository import AnalysisRepository
from error_analysis.reports.client import ReportProvider

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ClassificationResult:
    """
    The outcome of a classification run.

    :ivar reports_seen: the number of reports found within the classified time window
    :ivar reports_classified: the number of reports that were newly associated with an equivalence class
    :ivar classes_created: the number of equivalence classes that were newly created
    """

    reports_seen: int
    reports_classified: int
    classes_created: int


class ReportClassifier:
    """
    Associates error reports with equivalence classes.

    For each not-yet-classified report within a time window, the full report is retrieved,
    fingerprinted, and associated with the matching equivalence class (which is created on demand).
    Already-classified reports are skipped without retrieving their details.
    """

    def __init__(self, provider: ReportProvider, algorithm: FingerprintAlgorithm, repository: AnalysisRepository) -> None:
        """
        :param provider: the source of error reports
        :param algorithm: the fingerprint algorithm determining class membership
        :param repository: the store for classes and associations
        """
        self._provider = provider
        self._algorithm = algorithm
        self._repository = repository

    def classify_window(self, since: datetime, until: datetime | None = None) -> ClassificationResult:
        """
        Classifies all reports within the given time window.

        :param since: the oldest boundary of the window (exclusive)
        :param until: the newest boundary of the window (exclusive); unbounded if ``None``
        :return: the outcome of the run
        """
        # collect the report summaries within the window and drop already-classified reports
        summaries = list(self._provider.iter_summaries(since=since, until=until))
        already_classified = self._repository.associated_report_ids([s.id for s in summaries])
        pending = [s for s in summaries if s.id not in already_classified]
        log.info("classifying %d of %d reports in window (%d already classified)", len(pending), len(summaries), len(already_classified))

        # fingerprint and associate each pending report
        classes_created = 0
        for summary in pending:
            report = self._provider.get_report(summary.id)
            fingerprint = self._algorithm.fingerprint(report)
            resolution = self._repository.get_or_create_class(fingerprint, exemplar_hint=report.hint)
            if resolution.created:
                classes_created += 1
            self._repository.associate(report.id, resolution.equivalence_class.id, report_created_at=report.created_at)

        return ClassificationResult(reports_seen=len(summaries), reports_classified=len(pending), classes_created=classes_created)
