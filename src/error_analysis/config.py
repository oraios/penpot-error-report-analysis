"""Application-level configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from error_analysis.reports.client import PenpotApiCredentials


@dataclass(frozen=True)
class AppConfig:
    """
    The configuration of the analysis platform.

    :ivar db_file: the path of the SQLite database file holding the analysis data
    :ivar credentials: the connection parameters for the Penpot RPC API
    """

    db_file: Path
    credentials: PenpotApiCredentials

    _ENV_DB_FILE = "ERROR_ANALYSIS_DB"

    @classmethod
    def default(cls) -> AppConfig:
        """
        Creates the default configuration.

        The database file defaults to ``data/analysis.sqlite`` within the project repository and can be
        overridden via the ``ERROR_ANALYSIS_DB`` environment variable. API credentials are read from the
        environment, falling back to the enclosing Penpot repository's ``.env`` file if present.

        :return: the configuration
        """
        # determine the database file location
        project_root = Path(__file__).resolve().parents[2]
        db_file = Path(os.environ.get(cls._ENV_DB_FILE, project_root / "data" / "analysis.sqlite"))

        # read the API credentials, preferring the Penpot repository's .env file for discovery
        penpot_env = project_root.parent / ".env"
        credentials = PenpotApiCredentials.from_env(penpot_env if penpot_env.is_file() else None)

        return cls(db_file=db_file, credentials=credentials)
