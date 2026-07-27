"""Version 1 of the report fingerprint algorithm."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from error_analysis.fingerprint.algorithm import Fingerprint, FingerprintAlgorithm
from error_analysis.reports.model import BackendErrorReport, ErrorReport, FrontendErrorReport


class FingerprintAlgorithmV1(FingerprintAlgorithm):
    """
    The initial fingerprint algorithm.

    The signature document combines the normalized hint with shape-specific discriminators:

    * backend reports contribute the exception class chain and the leading stack frames of the root
      cause, with build-dependent parts (line numbers, generated function suffixes, object addresses)
      stripped; resource-exhaustion errors (e.g. ``OutOfMemoryError``) contribute no frames, as their
      stack traces are arbitrary,
    * frontend reports contribute the report kind and selected discriminator entries of the error data
      (``:type``, ``:code``, ``:fn``); the minified JavaScript stack trace is deliberately excluded, as
      its symbol names are not stable across builds.
    """

    _VERSION = 1

    _FRAME_COUNT = 8
    """the number of leading root-cause stack frames included in the signature"""

    _EXHAUSTION_EXCEPTION_CLASSES = frozenset({"java.lang.OutOfMemoryError", "java.lang.StackOverflowError"})
    """exception classes whose stack traces are arbitrary and therefore excluded from the signature"""

    @property
    def version(self) -> int:
        return self._VERSION

    def fingerprint(self, report: ErrorReport) -> Fingerprint:
        # assemble the shape-independent part of the signature document
        lines = [f"hint: {_HintNormalizer.normalize(report.hint)}"]

        # append the shape-specific discriminators
        match report:
            case BackendErrorReport():
                lines.extend(self._backend_lines(report))
            case FrontendErrorReport():
                lines.extend(self._frontend_lines(report))

        # derive the digest from the signature document
        signature = "\n".join(lines)
        digest = hashlib.sha256(signature.encode("utf-8")).hexdigest()
        return Fingerprint(digest=digest, signature=signature, algorithm_version=self._VERSION)

    @classmethod
    def _backend_lines(cls, report: BackendErrorReport) -> list[str]:
        """
        :param report: the backend report
        :return: the signature lines contributed by the report's stack trace
        """
        # parse the exception cause chain from the trace
        causes = _JvmTrace.parse(report.trace).causes
        lines = [f"exception: {cause.exception_class}" for cause in causes]

        # append the leading root-cause frames unless the trace is arbitrary
        arbitrary = any(cause.exception_class in cls._EXHAUSTION_EXCEPTION_CLASSES for cause in causes)
        if not arbitrary and causes:
            lines.extend(f"frame: {frame}" for frame in causes[0].frames[: cls._FRAME_COUNT])
        return lines

    @staticmethod
    def _frontend_lines(report: FrontendErrorReport) -> list[str]:
        """
        :param report: the frontend report
        :return: the signature lines contributed by the report's kind and error data
        """
        lines = []
        if report.kind is not None:
            lines.append(f"kind: {report.kind}")
        if (data := report.data_section) is not None:
            for key in ("type", "code", "fn"):
                if (value := _EdnData.entry(data, key)) is not None:
                    lines.append(f"data.{key}: {value}")
        return lines


class _HintNormalizer:
    """
    Normalizes hint texts by masking dynamic values.

    The rules mirror the hint normalization of ``scripts/error-reports.mjs`` so that hints normalize
    identically across both tools.
    """

    _UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE)
    _FILE_ID_RE = re.compile(r"\b(file[-_]?id)\b\s*[=:]\s*([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", re.IGNORECASE)
    _NUMERIC_ID_RE = re.compile(r"\(\d+\)")
    _ELAPSED_RE = re.compile(r"\b\d+(?:\.\d+)?(?:ms|s|m|h|d)(?:\s*\d+(?:\.\d+)?(?:ms|s|m|h|d))*\b")
    _QUOTED_URI_RE = re.compile(r"https?://\"[^\"]*\"")
    _URI_RE = re.compile(r"https?://\S+")
    _WHITESPACE_RE = re.compile(r"\s+")

    @classmethod
    def normalize(cls, hint: str) -> str:
        """
        :param hint: the hint text to normalize
        :return: the hint with dynamic values (UUIDs, numeric identifiers, durations, URIs) masked
            and whitespace collapsed; ``(empty)`` if nothing remains
        """
        # unify quote characters and collapse whitespace
        h = hint.replace("\u201c", '"').replace("\u201d", '"').replace("\u2018", "'").replace("\u2019", "'").replace('\\"', '"')
        h = cls._WHITESPACE_RE.sub(" ", h).strip()

        # mask dynamic values
        h = cls._QUOTED_URI_RE.sub("<uri>", h)
        h = cls._URI_RE.sub("<uri>", h)
        h = cls._FILE_ID_RE.sub(lambda m: f"{m.group(1)}: <file-id>", h)
        h = cls._UUID_RE.sub("<uuid>", h)
        h = cls._NUMERIC_ID_RE.sub("(<id>)", h)
        h = cls._ELAPSED_RE.sub("<elapsed>", h)

        # collapse whitespace potentially introduced by the substitutions
        h = cls._WHITESPACE_RE.sub(" ", h).strip()
        return h or "(empty)"


@dataclass(frozen=True)
class _TraceCause:
    """
    A single cause within a JVM exception cause chain.

    :ivar exception_class: the fully qualified class name of the exception
    :ivar frames: the normalized stack frames of the cause, innermost first
    """

    exception_class: str
    frames: list[str]


class _JvmTrace:
    """
    A parsed JVM stack trace in the textual format delivered by backend error reports.

    In that format, each cause is introduced by a line starting with an arrow
    (``→ exception.Class: message (File.java:123)``), followed by its stack frames (the first
    prefixed with ``at:``), one per line.
    """

    _CAUSE_RE = re.compile(r"^\u2192\s*(?P<cls>[\w.$]+)")
    _FRAME_PREFIX_RE = re.compile(r"^at:\s*")
    _LOCATION_RE = re.compile(r"\(.*?\)\s*$")
    _GENERATED_SUFFIX_RE = re.compile(r"__\d+")
    _OBJECT_ADDRESS_RE = re.compile(r"(@|0x)[0-9a-f]+", re.IGNORECASE)

    def __init__(self, causes: list[_TraceCause]) -> None:
        """
        :param causes: the parsed cause chain, root exception first
        """
        self.causes = causes

    @classmethod
    def parse(cls, trace: str | None) -> _JvmTrace:
        """
        Parses the given trace text.

        :param trace: the trace text; may be ``None`` or empty
        :return: the parsed trace, with an empty cause chain if no trace is present
        """
        causes: list[_TraceCause] = []

        # scan the trace line by line, opening a new cause at each arrow line
        for raw_line in (trace or "").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if (cause_match := cls._CAUSE_RE.match(line)) is not None:
                causes.append(_TraceCause(exception_class=cause_match.group("cls"), frames=[]))
            elif causes and (frame := cls._normalize_frame(line)) is not None:
                causes[-1].frames.append(frame)

        return cls(causes)

    @classmethod
    def _normalize_frame(cls, line: str) -> str | None:
        """
        :param line: a stack frame line, stripped of surrounding whitespace
        :return: the frame with build-dependent parts (source location, generated function suffixes,
            object addresses) removed, or ``None`` if the line carries no frame information
        """
        frame = cls._FRAME_PREFIX_RE.sub("", line)
        frame = cls._LOCATION_RE.sub("", frame).strip()
        frame = cls._GENERATED_SUFFIX_RE.sub("__N", frame)
        frame = cls._OBJECT_ADDRESS_RE.sub("@N", frame)
        return frame or None


class _EdnData:
    """
    Extraction of discriminator entries from EDN-formatted error data.
    """

    _ENTRY_RE_TEMPLATE = r":{key}\s+(?:\"(?P<quoted>[^\"]*)\"|(?P<plain>[^\s,}}]+))"

    @classmethod
    def entry(cls, data: str, key: str) -> str | None:
        """
        :param data: the EDN-formatted error data text
        :param key: the name of the keyword entry to extract (without the leading colon)
        :return: the entry's value with string quoting removed, or ``None`` if the entry is not present
        """
        match = re.search(cls._ENTRY_RE_TEMPLATE.format(key=re.escape(key)), data)
        if match is None:
            return None
        return match.group("quoted") if match.group("quoted") is not None else match.group("plain")
