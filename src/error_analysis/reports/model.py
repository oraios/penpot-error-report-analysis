"""Typed model of Penpot error reports."""

from __future__ import annotations

import re
from abc import ABC
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from uuid import UUID


class ReportSource(Enum):
    """
    The subsystem from which an error report originates.
    """

    LOGGING = "logging"
    AUDIT_LOG = "audit-log"
    RLIMIT = "rlimit"


@dataclass(frozen=True)
class ReportSummary:
    """
    A condensed view of an error report as returned by the report listing.

    :ivar id: the unique identifier of the report
    :ivar created_at: the instant at which the report was recorded
    :ivar source: the subsystem from which the report originates
    :ivar hint: the report's hint text (a short, human-readable error description)
    :ivar kind: the kind of error (e.g. ``unhandled-exception``), if reported
    :ivar tenant: the tenant on which the error occurred, if reported
    :ivar version: the backend version on which the error occurred, if reported
    :ivar profile_id: the identifier of the affected user profile, if reported
    """

    id: UUID
    created_at: datetime
    source: ReportSource
    hint: str
    kind: str | None = None
    tenant: str | None = None
    version: str | None = None
    profile_id: UUID | None = None


@dataclass(frozen=True)
class ErrorReport(ABC):
    """
    A fully detailed error report.

    Concrete subclasses represent the two report shapes delivered by the API:
    backend reports (:class:`BackendErrorReport`) and frontend reports
    (:class:`FrontendErrorReport`).

    :ivar id: the unique identifier of the report
    :ivar created_at: the instant at which the report was recorded
    :ivar source: the subsystem from which the report originates
    :ivar hint: the report's hint text (a short, human-readable error description)
    :ivar context_edn: the report's context metadata (host, tenant, versions, etc.) as an EDN-formatted string, if present
    """

    id: UUID
    created_at: datetime
    source: ReportSource
    hint: str
    context_edn: str | None


@dataclass(frozen=True)
class BackendErrorReport(ErrorReport):
    """
    An error report originating from the JVM backend.

    :ivar trace: the JVM stack trace, if present
    :ivar props_edn: additional log properties as an EDN-formatted string, if present
    :ivar params_edn: the parameters of the failing operation as an EDN-formatted string, if present
    """

    trace: str | None
    props_edn: str | None
    params_edn: str | None


@dataclass(frozen=True)
class FrontendErrorReport(ErrorReport):
    """
    An error report originating from the browser frontend.

    The report details are delivered as a single text blob (:attr:`report_text`) composed of named
    sections (``Context``, ``Data``, ``Trace``); accessors for the individual sections are provided.

    :ivar kind: the kind of error (e.g. ``exception-page``), if present
    :ivar origin: the origin of the report, if present
    :ivar report_text: the full report text blob, if present
    :ivar href: the frontend URL at which the error occurred, if present
    """

    _SECTION_HEADER_RE = re.compile(r"^([A-Za-z][A-Za-z ]*):\n-{4,}\n", re.MULTILINE)
    """matches a section header (a titled line underlined with dashes) within the report text blob"""
    _GROUP_SEPARATOR_RE = re.compile(r"^=+\s*$", re.MULTILINE)
    """matches a group separator line (a line of equals signs) within the report text blob"""

    kind: str | None
    origin: str | None
    report_text: str | None
    href: str | None

    @property
    def data_section(self) -> str | None:
        """
        The content of the report's ``Data`` section (an EDN representation of the error), if present.
        """
        return self._sections().get("Data")

    @property
    def trace_section(self) -> str | None:
        """
        The content of the report's ``Trace`` section (the JavaScript stack trace), if present.
        """
        return self._sections().get("Trace")

    def _sections(self) -> dict[str, str]:
        """
        :return: a mapping from section name to section content, parsed from the report text blob;
            empty if no report text is present
        """
        if self.report_text is None:
            return {}

        # locate all section headers within the blob
        headers = list(self._SECTION_HEADER_RE.finditer(self.report_text))

        # extract the content between consecutive headers, dropping group separator lines
        sections: dict[str, str] = {}
        for i, header in enumerate(headers):
            start = header.end()
            end = headers[i + 1].start() if i + 1 < len(headers) else len(self.report_text)
            content = self._GROUP_SEPARATOR_RE.sub("", self.report_text[start:end]).strip()
            sections[header.group(1)] = content
        return sections
