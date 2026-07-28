"""Retrieval of error reports from the Penpot RPC API."""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Any, Self
from uuid import UUID

import httpx
from dotenv import find_dotenv, load_dotenv

from error_analysis.reports.model import BackendErrorReport, ErrorReport, FrontendErrorReport, ReportSource, ReportSummary

log = logging.getLogger(__name__)


class ConfigurationError(Exception):
    """
    An error raised when required configuration is missing or invalid.
    """


class ReportProviderError(Exception):
    """
    An error raised when the retrieval of error reports fails.
    """


@dataclass(frozen=True)
class PenpotApiCredentials:
    """
    The connection parameters for the Penpot RPC API.

    :ivar api_uri: the base URI of the Penpot API (e.g. ``http://localhost:3450``)
    :ivar access_token: an access token holding the ``error-reports:read`` permission
    """

    api_uri: str
    access_token: str

    _ENV_API_URI = "PENPOT_API_URI"
    _ENV_ACCESS_TOKEN = "PENPOT_ACCESS_TOKEN"  # noqa: S105 (name of the environment variable, not a secret)

    @classmethod
    def from_env(cls, env_file: Path | None = None) -> Self:
        """
        Creates credentials from environment variables, additionally loading them from a ``.env`` file.

        :param env_file: the ``.env`` file to load; if ``None``, the file is discovered by searching upwards
            from the current working directory
        :return: the credentials
        :raises ConfigurationError: if a required variable is not set
        """
        # load variables from the .env file into the process environment
        load_dotenv(env_file if env_file is not None else find_dotenv(usecwd=True))

        # read and validate the required variables
        api_uri = os.environ.get(cls._ENV_API_URI)
        access_token = os.environ.get(cls._ENV_ACCESS_TOKEN)
        if not api_uri or not access_token:
            raise ConfigurationError(
                f"Both {cls._ENV_API_URI} and {cls._ENV_ACCESS_TOKEN} must be set (via the environment or a .env file)"
            )
        return cls(api_uri=api_uri.rstrip("/"), access_token=access_token)


class ReportProvider(ABC):
    """
    A source of Penpot error reports.
    """

    @abstractmethod
    def iter_summaries(self, since: datetime, until: datetime | None = None) -> Iterator[ReportSummary]:
        """
        Iterates over the summaries of all reports within the given time window, in ascending order of creation.

        :param since: the oldest boundary of the window (exclusive)
        :param until: the newest boundary of the window (exclusive); unbounded if ``None``
        :return: an iterator over the report summaries
        """

    @abstractmethod
    def get_report(self, report_id: UUID) -> ErrorReport:
        """
        Retrieves the full report with the given identifier.

        :param report_id: the identifier of the report
        :return: the full report
        """


class RpcReportProvider(ReportProvider):
    """
    A report provider backed by the Penpot RPC API.

    Report listings are retrieved concurrently by splitting the requested time window into
    disjoint shards that are paged in parallel (the listing endpoint's cursor pagination is
    inherently sequential within a single stream).

    Instances hold an HTTP connection pool and should be closed after use; the class supports
    the context manager protocol.
    """

    _PAGE_SIZE = 200
    """the maximum page size accepted by the listing endpoint"""

    def __init__(self, credentials: PenpotApiCredentials, timeout_seconds: float = 30.0, listing_concurrency: int = 8) -> None:
        """
        :param credentials: the connection parameters for the Penpot RPC API
        :param timeout_seconds: the timeout applied to each HTTP request
        :param listing_concurrency: the number of time shards into which listings are split for
            concurrent retrieval
        """
        self._listing_concurrency = max(1, listing_concurrency)
        self._http = httpx.Client(
            base_url=f"{credentials.api_uri}/api/main/methods/",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": f"Token {credentials.access_token}",
            },
            timeout=timeout_seconds,
        )

    def close(self) -> None:
        """
        Closes the underlying HTTP connection pool.
        """
        self._http.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None) -> None:
        self.close()

    def iter_summaries(self, since: datetime, until: datetime | None = None) -> Iterator[ReportSummary]:
        # split the window into disjoint time shards
        # (a shard's exclusive until boundary meets the next shard's since boundary exactly, as the
        # server compares (created_at, id) tuples: until=t excludes instant t, since=t includes it)
        effective_until = until if until is not None else datetime.now(UTC)
        boundaries = self._shard_boundaries(since, effective_until, self._listing_concurrency)

        # page all shards concurrently and deliver their results in chronological order
        with ThreadPoolExecutor(max_workers=len(boundaries) - 1, thread_name_prefix="summary-listing") as executor:
            shards = executor.map(self._list_shard, boundaries[:-1], boundaries[1:])
            for shard in shards:
                yield from shard

    def _list_shard(self, since: datetime, until: datetime) -> list[ReportSummary]:
        """
        Retrieves the summaries of a single time shard by sequentially following the pagination cursor.

        :param since: the oldest boundary of the shard (exclusive)
        :param until: the newest boundary of the shard (exclusive)
        :return: the summaries of the shard, in ascending order of creation
        """
        params: dict[str, Any] = {"limit": self._PAGE_SIZE, "since": self._format_instant(since), "until": self._format_instant(until)}
        summaries: list[ReportSummary] = []
        while True:
            result = self._rpc("get-error-reports", params)
            summaries.extend(self._parse_summary(item) for item in result["items"])
            if not (result.get("nextSince") and result.get("nextId")):
                return summaries
            params["since"] = result["nextSince"]
            params["since-id"] = result["nextId"]

    @staticmethod
    def _shard_boundaries(since: datetime, until: datetime, shard_count: int) -> list[datetime]:
        """
        :param since: the oldest boundary of the window
        :param until: the newest boundary of the window
        :param shard_count: the desired number of shards
        :return: the shard boundary instants (``shard_count + 1`` values from ``since`` to ``until``,
            uniformly spaced; fewer for degenerate windows)
        """
        if until <= since:
            return [since, until]
        step = (until - since) / shard_count
        return [since + i * step for i in range(shard_count)] + [until]

    def get_report(self, report_id: UUID) -> ErrorReport:
        data = self._rpc("get-error-report", {"id": str(report_id)})
        return self._parse_report(data)

    def _rpc(self, method: str, params: dict[str, Any]) -> Any:
        """
        Performs a single RPC call.

        :param method: the name of the RPC method
        :param params: the parameters to pass in the request body
        :return: the decoded JSON response
        :raises ReportProviderError: if the request fails or the server responds with an error status
        """
        # perform the HTTP request
        try:
            response = self._http.post(method, json=params)
        except httpx.HTTPError as e:
            raise ReportProviderError(f"RPC call '{method}' failed: {e}") from e

        # translate error responses into exceptions
        if response.is_error:
            try:
                error_data = response.json()
            except ValueError:
                error_data = {}
            code = error_data.get("code", response.status_code)
            message = error_data.get("message") or error_data.get("hint") or response.reason_phrase
            raise ReportProviderError(f"RPC call '{method}' failed [{code}]: {message}")

        return response.json()

    @classmethod
    def _parse_summary(cls, item: dict[str, Any]) -> ReportSummary:
        """
        :param item: a report listing item as returned by the API
        :return: the corresponding summary
        """
        profile_id = item.get("profileId")
        return ReportSummary(
            id=UUID(item["id"]),
            created_at=cls._parse_instant(item["createdAt"]),
            source=ReportSource(item["source"]),
            hint=item.get("hint") or "",
            kind=item.get("kind"),
            tenant=item.get("tenant"),
            version=item.get("version"),
            profile_id=UUID(profile_id) if profile_id else None,
        )

    @classmethod
    def _parse_report(cls, data: dict[str, Any]) -> ErrorReport:
        """
        :param data: a full report as returned by the API
        :return: the corresponding report model instance, the concrete type being determined by the report shape
        """
        # collect the fields shared by both report shapes
        common: dict[str, Any] = {
            "id": UUID(data["id"]),
            "created_at": cls._parse_instant(data["createdAt"]),
            "source": ReportSource(data["source"]),
            "hint": data.get("hint") or "",
            "context_edn": data.get("context"),
        }

        # discriminate the report shape by the presence of the frontend report blob
        if "report" in data:
            return FrontendErrorReport(
                **common,
                kind=data.get("kind"),
                origin=data.get("origin"),
                report_text=data.get("report"),
                href=data.get("href"),
            )
        return BackendErrorReport(
            **common,
            trace=data.get("trace"),
            props_edn=data.get("props"),
            params_edn=data.get("params"),
        )

    @staticmethod
    def _format_instant(instant: datetime) -> str:
        """
        :param instant: the instant to format; a naive value is interpreted as UTC
        :return: the instant as an ISO-8601 UTC timestamp accepted by the API
        """
        if instant.tzinfo is None:
            instant = instant.replace(tzinfo=UTC)
        return instant.astimezone(UTC).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _parse_instant(value: str) -> datetime:
        """
        :param value: an ISO-8601 timestamp as returned by the API
        :return: the corresponding timezone-aware instant
        """
        return datetime.fromisoformat(value)
