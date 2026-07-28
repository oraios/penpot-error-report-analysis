"""The MCP tools of the analysis platform."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from error_analysis.mcp.tools_base import Tool, ToolCallError
from error_analysis.serialization import JsonSerializer

_ANALYSIS_INSTRUCTIONS = """\
You are to analyze Penpot error report equivalence classes. For each class listed under 'classes' (in order):
1. Inspect the class's fingerprint signature (already included) to understand the error at a glance.
2. Retrieve the details of a concrete member report via get_report_details, using the most recent member id
   from 'recent_member_ids'. Retrieve further members via get_equivalence_class if one instance is inconclusive.
3. Investigate the root cause in the Penpot codebase using the code analysis tools at your disposal
   (symbol search, memories, REPL evaluation, git history).
4. Write a markdown report with the sections: Summary, Root Cause, Evidence, Affected Code,
   Suggested Fix, Severity. If the analysis remains inconclusive, report your findings and open questions instead.
5. Store the report via store_insight (passing the id of the report instance you analyzed and your model name as author).
Then continue with the next class. Do not skip storing an insight for an analyzed class."""


class BootstrapAnalysisTool(Tool):
    """
    Bootstraps an analysis session.
    """

    def apply(self, num_classes: int = 3, days: int = 7, max_reports: int = 1000) -> str:
        """
        Classifies the error reports of the recent past into equivalence classes and returns the most
        frequent classes that lack analysis insights, together with workflow instructions for analyzing them.
        This is the entry point of an analysis session; call it once and then follow the returned instructions.
        To bound the call's duration, at most max_reports not-yet-classified reports are processed (newest
        first); if this truncates the run, the result is marked accordingly, and completing the window via
        the error-analysis-classify command line is advisable (afterwards, this tool is fast for any window).

        :param num_classes: the number of unanalyzed equivalence classes to return for analysis
        :param days: the number of past days whose reports are to be classified and counted
        :param max_reports: the maximum number of not-yet-classified reports to classify during this call
        :return: a JSON object carrying the workflow instructions and the classes to analyze
        """
        # associate the window's reports with equivalence classes, bounded by the report limit
        since = datetime.now(UTC) - timedelta(days=days)
        result = self._context.create_classifier().classify_window(since=since, max_new_reports=max_reports)

        # select the most frequent classes without insights
        overviews = self._context.repository.list_class_overviews(count_since=since)
        unanalyzed = [o for o in overviews if o.insight_count == 0][:num_classes]

        # attach recent member report ids to each selected class
        classes = []
        for overview in unanalyzed:
            members = self._context.repository.member_report_ids(overview.equivalence_class.id, limit=5)
            entry = JsonSerializer.class_overview(overview)
            entry["recent_member_ids"] = [str(report_id) for report_id, _ in members]
            classes.append(entry)

        # describe the classification run, flagging truncation
        classification_run: dict[str, object] = {
            "window_days": days,
            "reports_seen": result.reports_seen,
            "reports_pending": result.reports_pending,
            "reports_newly_classified": result.reports_classified,
            "classes_newly_created": result.classes_created,
            "truncated": result.truncated,
        }
        if result.truncated:
            classification_run["note"] = (
                "The report limit truncated classification, so report counts are lower bounds; "
                "complete the window via the error-analysis-classify command line."
            )

        return self._to_json(
            {
                "classification_run": classification_run,
                "instructions": _ANALYSIS_INSTRUCTIONS,
                "classes": classes,
            }
        )


class ListClassOverviewsTool(Tool):
    """
    Lists equivalence class overviews.
    """

    def apply(self, days: int = 30) -> str:
        """
        Lists all equivalence classes with reports in the recent past, ordered by report count descending.
        Note that report counts reflect the given time window, and only classes with reports in the window are listed.

        :param days: the number of past days that reports must fall into to be counted
        :return: a JSON array of class overviews
        """
        since = datetime.now(UTC) - timedelta(days=days)
        overviews = self._context.repository.list_class_overviews(count_since=since)
        return self._to_json([JsonSerializer.class_overview(o) for o in overviews])


class GetEquivalenceClassTool(Tool):
    """
    Retrieves an equivalence class.
    """

    def apply(self, class_id: int, member_limit: int = 20) -> str:
        """
        Retrieves an equivalence class, including its fingerprint signature, stored insights,
        and the ids of its most recent member reports.

        :param class_id: the id of the equivalence class
        :param member_limit: the maximum number of recent member report ids to include
        :return: a JSON object describing the class
        """
        # retrieve the class
        record = self._context.repository.get_class(class_id)
        if record is None:
            raise ToolCallError(f"No equivalence class with id {class_id} exists")

        # assemble the class description with members and insights
        members = self._context.repository.member_report_ids(class_id, limit=member_limit)
        insights = self._context.repository.list_insights(class_id)
        return self._to_json(
            {
                **JsonSerializer.equivalence_class(record),
                "recent_members": [
                    {"report_id": str(report_id), "created_at": created_at.isoformat()} for report_id, created_at in members
                ],
                "insights": [JsonSerializer.insight(i) for i in insights],
            }
        )


class GetReportDetailsTool(Tool):
    """
    Retrieves the details of an error report.
    """

    def apply(self, report_id: str) -> str:
        """
        Retrieves the full details of an error report, including its stack trace and context metadata.

        :param report_id: the id (UUID) of the error report
        :return: a JSON object with the report details
        """
        report = self._context.provider.get_report(self._parse_uuid(report_id))
        return self._to_json(JsonSerializer.report(report))


class StoreInsightTool(Tool):
    """
    Stores an analysis insight.
    """

    def apply(self, class_id: int, analyzed_report_id: str, markdown: str, author: str = "") -> str:
        """
        Stores a markdown analysis report as an insight for an equivalence class.

        :param class_id: the id of the equivalence class the insight pertains to
        :param analyzed_report_id: the id (UUID) of the concrete report instance that was analyzed
        :param markdown: the analysis report in markdown format (sections: Summary, Root Cause, Evidence,
            Affected Code, Suggested Fix, Severity)
        :param author: the author of the insight, e.g. the analyzing LLM's model name
        :return: a JSON object describing the stored insight
        """
        # validate the referenced class
        if self._context.repository.get_class(class_id) is None:
            raise ToolCallError(f"No equivalence class with id {class_id} exists")

        # store the insight
        insight = self._context.repository.add_insight(
            class_id=class_id,
            analyzed_report_id=self._parse_uuid(analyzed_report_id),
            markdown=markdown,
            author=author or None,
        )
        return self._to_json(JsonSerializer.insight(insight))
