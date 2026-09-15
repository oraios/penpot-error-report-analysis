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
    :ivar github_repository: the ``owner/name`` slug of the GitHub repository issues are filed in
    """

    db_file: Path
    credentials: PenpotApiCredentials
    github_repository: str = "penpot/penpot"

    _ENV_DB_FILE = "ERROR_ANALYSIS_DB"
    _ENV_GITHUB_REPOSITORY = "ERROR_ANALYSIS_GITHUB_REPOSITORY"

    @classmethod
    def default(cls) -> AppConfig:
        """
        Creates the default configuration.

        The database file defaults to ``data/analysis.sqlite`` within the project repository and can be
        overridden via the ``ERROR_ANALYSIS_DB`` environment variable. API credentials are read from the
        environment, falling back to the enclosing Penpot repository's ``.env`` file if present.
        The GitHub repository issues are filed in can be overridden via the
        ``ERROR_ANALYSIS_GITHUB_REPOSITORY`` environment variable.

        :return: the configuration
        """
        # determine the database file location
        project_root = Path(__file__).resolve().parents[2]
        db_file = Path(os.environ.get(cls._ENV_DB_FILE, project_root / "data" / "analysis.sqlite"))

        # read the API credentials, preferring the Penpot repository's .env file for discovery
        penpot_env = project_root.parent / ".env"
        credentials = PenpotApiCredentials.from_env(penpot_env if penpot_env.is_file() else None)

        # read the GitHub repository issues are filed in
        github_repository = os.environ.get(cls._ENV_GITHUB_REPOSITORY)

        if github_repository:
            return cls(db_file=db_file, credentials=credentials, github_repository=github_repository)
        return cls(db_file=db_file, credentials=credentials)
