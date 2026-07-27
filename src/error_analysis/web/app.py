"""The Flask backend serving the dashboard and its JSON API."""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime, timedelta
from typing import Any

from flask import Flask, Response, jsonify, request

from error_analysis.context import AnalysisContext
from error_analysis.serialization import JsonSerializer

log = logging.getLogger(__name__)


class WebBackend:
    """
    The web application of the analysis platform.

    Serves the static dashboard at the root path and provides the JSON endpoints the dashboard
    consumes: class overviews, class details (with insights and members), and report details.
    """

    _DEFAULT_WINDOW_DAYS = 30

    def __init__(self, context: AnalysisContext) -> None:
        """
        :param context: the platform services the endpoints operate on
        """
        self._context = context
        self._app = Flask(__name__)
        self._register_routes()

    @property
    def flask_app(self) -> Flask:
        """
        The configured Flask application.
        """
        return self._app

    def _register_routes(self) -> None:
        """
        Registers all routes with the Flask application.
        """
        self._app.add_url_rule("/", view_func=self._index)
        self._app.add_url_rule("/api/classes", view_func=self._list_classes)
        self._app.add_url_rule("/api/classes/<int:class_id>", view_func=self._get_class)
        self._app.add_url_rule("/api/reports/<report_id>", view_func=self._get_report)

    def _index(self) -> Response:
        return self._app.send_static_file("index.html")

    def _list_classes(self) -> Any:
        """
        Delivers the class overviews for the requested time window (query parameter ``days``),
        ordered by report count descending.
        """
        # determine the requested window
        try:
            days = int(request.args.get("days", self._DEFAULT_WINDOW_DAYS))
        except ValueError:
            return jsonify({"error": "query parameter 'days' must be an integer"}), 400
        since = datetime.now(UTC) - timedelta(days=days)

        # deliver the overviews
        overviews = self._context.repository.list_class_overviews(count_since=since)
        return jsonify([JsonSerializer.class_overview(o) for o in overviews])

    def _get_class(self, class_id: int) -> Any:
        """
        Delivers the details of an equivalence class: the class itself, its insights, and its
        most recent members.
        """
        record = self._context.repository.get_class(class_id)
        if record is None:
            return jsonify({"error": f"no equivalence class with id {class_id}"}), 404

        members = self._context.repository.member_report_ids(class_id, limit=50)
        insights = self._context.repository.list_insights(class_id)
        return jsonify(
            {
                **JsonSerializer.equivalence_class(record),
                "members": [{"report_id": str(report_id), "created_at": created_at.isoformat()} for report_id, created_at in members],
                "insights": [JsonSerializer.insight(i) for i in insights],
            }
        )

    def _get_report(self, report_id: str) -> Any:
        """
        Delivers the full details of an error report, retrieved live from the report source.
        """
        from uuid import UUID

        try:
            parsed_id = UUID(report_id)
        except ValueError:
            return jsonify({"error": f"invalid report id '{report_id}'"}), 400
        return jsonify(JsonSerializer.report(self._context.provider.get_report(parsed_id)))


def main() -> None:
    """
    Runs the web backend as a development server.

    The port is read from the ``ERROR_ANALYSIS_WEB_PORT`` environment variable (default 5100).
    """
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-5s %(name)s: %(message)s")
    port = int(os.environ.get("ERROR_ANALYSIS_WEB_PORT", "5100"))
    backend = WebBackend(AnalysisContext.create_default())
    backend.flask_app.run(host="127.0.0.1", port=port)
