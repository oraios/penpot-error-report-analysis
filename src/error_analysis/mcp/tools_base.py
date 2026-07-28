"""The base abstraction for MCP tools, modeled after Serena's tool framework."""

from __future__ import annotations

import json
import logging
from abc import ABC
from typing import TYPE_CHECKING, Any, Protocol
from uuid import UUID

from mcp.server.fastmcp.utilities.func_metadata import FuncMetadata, func_metadata

if TYPE_CHECKING:
    from error_analysis.context import AnalysisContext

log = logging.getLogger(__name__)


class ToolCallError(Exception):
    """
    An error raised when a tool call fails; its message is reported to the calling LLM.
    """


class _ApplyMethod(Protocol):
    """
    The protocol of a tool's ``apply`` method (arbitrary keyword parameters, string result).
    """

    def __call__(self, *args: Any, **kwargs: Any) -> str: ...


class Tool(ABC):  # noqa: B024 (the apply method cannot be declared abstract, as its signature is tool-specific)
    """
    An MCP tool operating on the analysis platform.

    Each concrete tool implements an ``apply`` method whose typed signature and docstring define the
    tool's parameter schema and description as presented to the LLM. The tool's name is derived from
    the class name (``FooBarTool`` becomes ``foo_bar``).
    """

    def __init__(self, context: AnalysisContext) -> None:
        """
        :param context: the platform services the tool operates on
        """
        self._context = context

    @classmethod
    def get_name(cls) -> str:
        """
        :return: the tool's name, derived from the class name by dropping the ``Tool`` suffix and
            converting to snake case
        """
        name = cls.__name__.removesuffix("Tool")
        return "".join("_" + c.lower() if c.isupper() else c for c in name).lstrip("_")

    @classmethod
    def get_apply_docstring(cls) -> str:
        """
        :return: the docstring of the tool's ``apply`` method
        :raises AttributeError: if the method is not defined or carries no docstring
        """
        apply_fn = cls._get_apply_fn_static()
        if not apply_fn.__doc__:
            raise AttributeError(f"apply method of {cls.__name__} has no docstring")
        return apply_fn.__doc__.strip()

    @classmethod
    def get_apply_fn_metadata(cls) -> FuncMetadata:
        """
        :return: the schema metadata of the tool's ``apply`` method, as used by the MCP server
        """
        return func_metadata(cls._get_apply_fn_static(), skip_names=["self"])

    def apply_ex(self, **kwargs: Any) -> str:
        """
        Applies the tool with logging and uniform error handling.

        :param kwargs: the tool call arguments
        :return: the tool's result
        :raises ToolCallError: if the tool application fails
        """
        # log the call
        log.info("Applying tool %s with arguments: %s", self.get_name(), kwargs)

        # apply the tool, translating failures into tool call errors
        try:
            result = self._get_apply_fn()(**kwargs)
        except ToolCallError:
            raise
        except Exception as e:
            message = f"{e.__class__.__name__}: {e}"
            log.error(message, exc_info=e)
            raise ToolCallError(message) from e

        log.info("Tool %s completed (%d chars)", self.get_name(), len(result))
        return result

    def _get_apply_fn(self) -> _ApplyMethod:
        """
        :return: the bound ``apply`` method of this tool instance
        :raises AttributeError: if the method is not defined
        """
        apply_fn: _ApplyMethod | None = getattr(self, "apply", None)
        if apply_fn is None:
            raise AttributeError(f"apply method not defined in {self.__class__.__name__}")
        return apply_fn

    @classmethod
    def _get_apply_fn_static(cls) -> Any:
        """
        :return: the unbound ``apply`` method of this tool class
        :raises AttributeError: if the method is not defined
        """
        apply_fn = getattr(cls, "apply", None)
        if apply_fn is None:
            raise AttributeError(f"apply method not defined in {cls.__name__}")
        return apply_fn

    @staticmethod
    def _parse_uuid(value: str) -> UUID:
        """
        :param value: the UUID string to parse
        :return: the parsed UUID
        :raises ToolCallError: if the value is not a valid UUID
        """
        try:
            return UUID(value)
        except ValueError as e:
            raise ToolCallError(f"Invalid id '{value}': {e}") from e

    @staticmethod
    def _to_json(data: Any) -> str:
        """
        :param data: the data to serialize
        :return: the data as a JSON string
        """
        return json.dumps(data, ensure_ascii=False, indent=2)
