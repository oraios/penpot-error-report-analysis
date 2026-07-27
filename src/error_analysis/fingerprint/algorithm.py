"""Abstractions for error report fingerprinting."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from error_analysis.reports.model import ErrorReport


@dataclass(frozen=True)
class Fingerprint:
    """
    The result of fingerprinting an error report.

    :ivar digest: the SHA-256 hex digest of the signature document, identifying the equivalence class
    :ivar signature: the normalized signature document from which the digest was computed; retained for explainability
    :ivar algorithm_version: the version of the algorithm that produced the fingerprint
    """

    digest: str
    signature: str
    algorithm_version: int


class FingerprintAlgorithm(ABC):
    """
    An algorithm computing version-stable fingerprints for error reports.

    Reports with equal fingerprint digests are considered to pertain to the same underlying issue.
    Algorithms are versioned; associations computed with an older version can be recomputed when the
    algorithm evolves.
    """

    @property
    @abstractmethod
    def version(self) -> int:
        """
        The version of the algorithm.
        """

    @abstractmethod
    def fingerprint(self, report: ErrorReport) -> Fingerprint:
        """
        Computes the fingerprint of the given report.

        :param report: the report to fingerprint
        :return: the fingerprint
        """
