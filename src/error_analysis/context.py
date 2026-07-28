"""The aggregation of the platform services used by delivery layers."""

from __future__ import annotations

from error_analysis.classify.workflow import ReportClassifier
from error_analysis.config import AppConfig
from error_analysis.fingerprint.algorithm import FingerprintAlgorithm
from error_analysis.fingerprint.v1 import FingerprintAlgorithmV1
from error_analysis.persistence.repository import AnalysisRepository
from error_analysis.persistence.sql import SqlAnalysisRepository
from error_analysis.reports.client import ReportProvider, RpcReportProvider


class AnalysisContext:
    """
    The platform services operated on by the delivery layers (MCP server and web backend).
    """

    def __init__(self, provider: ReportProvider, repository: AnalysisRepository, algorithm: FingerprintAlgorithm) -> None:
        """
        :param provider: the source of error reports
        :param repository: the store for classes, associations, and insights
        :param algorithm: the fingerprint algorithm determining class membership
        """
        self.provider = provider
        self.repository = repository
        self.algorithm = algorithm

    @classmethod
    def create_default(cls, config: AppConfig | None = None) -> AnalysisContext:
        """
        Creates a context with the default service implementations (RPC report provider,
        SQLite-backed repository, current fingerprint algorithm).

        :param config: the configuration to use; the default configuration if ``None``
        :return: the context
        """
        config = config if config is not None else AppConfig.default()
        return cls(
            provider=RpcReportProvider(config.credentials),
            repository=SqlAnalysisRepository.for_sqlite(config.db_file),
            algorithm=FingerprintAlgorithmV1(),
        )

    def create_classifier(self, fetch_concurrency: int = 8) -> ReportClassifier:
        """
        :param fetch_concurrency: the number of report detail retrievals to perform concurrently
        :return: a classifier wired to the context's services
        """
        return ReportClassifier(self.provider, self.algorithm, self.repository, fetch_concurrency=fetch_concurrency)
