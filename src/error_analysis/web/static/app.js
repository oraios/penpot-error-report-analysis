/**
 * Penpot error report analysis dashboard.
 *
 * Object-oriented structure: ApiClient (server communication), ClassListView (left pane),
 * ClassDetailView (right pane), ReportOverlay (member report inspection), App (wiring).
 */
"use strict";

/** Communicates with the JSON API of the analysis backend. */
class ApiClient {
    /**
     * @param {number} days the time window in days
     * @returns {Promise<Array>} the class overviews
     */
    listClasses(days) {
        return $.getJSON("/api/classes", { days: days });
    }

    /**
     * @param {number} classId the id of the equivalence class
     * @returns {Promise<Object>} the class details (class, insights, members)
     */
    getClass(classId) {
        return $.getJSON(`/api/classes/${classId}`);
    }

    /**
     * @param {string} reportId the id of the error report
     * @returns {Promise<Object>} the report details
     */
    getReport(reportId) {
        return $.getJSON(`/api/reports/${reportId}`);
    }
}

/** Renders the table of equivalence classes and reports row selection. */
class ClassListView {
    /**
     * @param {jQuery} $tbody the table body to render rows into
     * @param {jQuery} $emptyNote the note shown when no classes exist
     * @param {jQuery} $countLabel the label showing the class count
     * @param {function(number): void} onSelect invoked with the class id when a row is selected
     */
    constructor($tbody, $emptyNote, $countLabel, onSelect) {
        this._$tbody = $tbody;
        this._$emptyNote = $emptyNote;
        this._$countLabel = $countLabel;
        this._onSelect = onSelect;
    }

    /**
     * Renders the given class overviews.
     * @param {Array} overviews the class overviews, ordered by report count descending
     */
    render(overviews) {
        this._$tbody.empty();
        this._$emptyNote.toggleClass("hidden", overviews.length > 0);
        this._$countLabel.text(`${overviews.length} classes`);
        overviews.forEach((overview) => this._$tbody.append(this._buildRow(overview)));
    }

    /**
     * Highlights the row of the given class as selected.
     * @param {number} classId the id of the selected class
     */
    markSelected(classId) {
        this._$tbody.find("tr").removeClass("selected");
        this._$tbody.find(`tr[data-class-id='${classId}']`).addClass("selected");
    }

    /**
     * @param {Object} overview the class overview to build a row for
     * @returns {jQuery} the table row
     */
    _buildRow(overview) {
        const analyzed = overview.insight_count > 0;
        const $status = $("<span>")
            .addClass("badge")
            .addClass(analyzed ? "done" : "pending")
            .text(analyzed ? `${overview.insight_count} insight${overview.insight_count > 1 ? "s" : ""}` : "pending");
        const $row = $("<tr>")
            .attr("data-class-id", overview.id)
            .append($("<td>").addClass("col-id").text(overview.id))
            .append($("<td>").addClass("hint-cell").text(overview.exemplar_hint || "(no hint)"))
            .append($("<td>").addClass("col-num").text(overview.report_count))
            .append($("<td>").addClass("col-date").text(Formats.date(overview.last_seen_at)))
            .append($("<td>").addClass("col-status").append($status));
        $row.on("click", () => this._onSelect(overview.id));
        return $row;
    }
}

/** Renders the details of a selected equivalence class. */
class ClassDetailView {
    /**
     * @param {jQuery} $pane the pane to render into
     * @param {function(string): void} onReportOpen invoked with the report id when a member is opened
     */
    constructor($pane, onReportOpen) {
        this._$pane = $pane;
        this._onReportOpen = onReportOpen;
    }

    /**
     * Renders the given class details.
     * @param {Object} detail the class details (class fields, insights, members)
     */
    render(detail) {
        this._$pane.empty();
        this._$pane
            .append(this._buildHeader(detail))
            .append(this._buildInsightsSection(detail.insights))
            .append(this._buildSection("Fingerprint signature", $("<pre>").addClass("code-block").text(detail.signature)))
            .append(this._buildMembersSection(detail.members));
    }

    /**
     * @param {Object} detail the class details
     * @returns {jQuery} the header element (hint title and metadata line)
     */
    _buildHeader(detail) {
        const $meta = $("<div>").addClass("detail-meta")
            .append($("<span>").text(`class #${detail.id}`))
            .append($("<span>").text(`first seen ${Formats.date(detail.first_seen_at)}`))
            .append($("<span>").text(`last seen ${Formats.date(detail.last_seen_at)}`))
            .append($("<span>").text(`fingerprint v${detail.algorithm_version}`))
            .append($("<span>").attr("title", detail.digest).text(`digest ${detail.digest.substring(0, 12)}…`));
        return $("<div>").addClass("detail-header")
            .append($("<h2>").text(detail.exemplar_hint || "(no hint)"))
            .append($meta);
    }

    /**
     * @param {Array} insights the insights of the class
     * @returns {jQuery} the insights section
     */
    _buildInsightsSection(insights) {
        if (insights.length === 0) {
            const $note = $("<p>").addClass("no-insights")
                .text("Not yet analyzed. Run an analysis session via the MCP server to gather insights.");
            return this._buildSection("Insights", $note);
        }
        const $insights = insights.map((insight) => this._buildInsight(insight));
        return this._buildSection("Insights", $insights);
    }

    /**
     * @param {Object} insight the insight to render
     * @returns {jQuery} the insight card, with markdown content rendered to HTML
     */
    _buildInsight(insight) {
        const author = insight.author ? ` by ${insight.author}` : "";
        const $reportLink = $("<a>")
            .attr("href", "#")
            .text(insight.analyzed_report_id)
            .on("click", (event) => {
                event.preventDefault();
                this._onReportOpen(insight.analyzed_report_id);
            });
        const $meta = $("<p>").addClass("insight-meta")
            .text(`${Formats.dateTime(insight.created_at)}${author} — analyzed report `)
            .append($reportLink);
        return $("<article>").addClass("insight")
            .append($("<div>").addClass("insight-content").html(marked.parse(insight.markdown)))
            .append($meta);
    }

    /**
     * @param {Array} members the member reports of the class
     * @returns {jQuery} the members section
     */
    _buildMembersSection(members) {
        const $list = $("<ul>").addClass("member-list");
        members.forEach((member) => {
            const $link = $("<a>")
                .attr("href", "#")
                .text(member.report_id)
                .on("click", (event) => {
                    event.preventDefault();
                    this._onReportOpen(member.report_id);
                });
            $list.append(
                $("<li>")
                    .append($("<span>").addClass("member-date").text(Formats.dateTime(member.created_at)))
                    .append($link)
            );
        });
        return this._buildSection(`Member reports (${members.length} most recent)`, $list);
    }

    /**
     * @param {string} title the section title
     * @param {jQuery|Array} $content the section content
     * @returns {jQuery} the section element
     */
    _buildSection(title, $content) {
        return $("<section>").addClass("detail-section").append($("<h3>").text(title)).append($content);
    }
}

/** Shows the details of a single error report in an overlay. */
class ReportOverlay {
    /**
     * @param {jQuery} $overlay the overlay root element
     */
    constructor($overlay) {
        this._$overlay = $overlay;
        this._$title = $overlay.find("#report-title");
        this._$body = $overlay.find("#report-body");
        $overlay.find("#report-close").on("click", () => this.hide());
        $overlay.on("click", (event) => {
            if (event.target === $overlay.get(0)) this.hide();
        });
        $(document).on("keydown", (event) => {
            if (event.key === "Escape") this.hide();
        });
    }

    /**
     * Shows the given report.
     * @param {Object} report the report details
     */
    show(report) {
        this._$title.text(`${report.shape} report ${report.id}`);
        this._$body.empty()
            .append(this._section("Created", $("<p>").text(Formats.dateTime(report.created_at))))
            .append(this._section("Hint", $("<pre>").addClass("code-block").text(report.hint || "(none)")));
        this._appendShapeSections(report);
        this._appendOptionalCode("Context", report.context_edn);
        this._$overlay.removeClass("hidden");
    }

    /** Hides the overlay. */
    hide() {
        this._$overlay.addClass("hidden");
    }

    /**
     * Appends the sections specific to the report shape.
     * @param {Object} report the report details
     */
    _appendShapeSections(report) {
        if (report.shape === "backend") {
            this._appendOptionalCode("Trace", report.trace);
            this._appendOptionalCode("Props", report.props_edn);
            this._appendOptionalCode("Params", report.params_edn);
        } else {
            this._appendOptionalCode("Error data", report.data_section);
            this._appendOptionalCode("Trace", report.trace_section);
            this._appendOptionalCode("Location", report.href);
        }
    }

    /**
     * Appends a code section if the given content is present.
     * @param {string} title the section title
     * @param {?string} content the section content
     */
    _appendOptionalCode(title, content) {
        if (content) {
            this._$body.append(this._section(title, $("<pre>").addClass("code-block").text(content)));
        }
    }

    /**
     * @param {string} title the section title
     * @param {jQuery} $content the section content
     * @returns {jQuery} the section element
     */
    _section(title, $content) {
        return $("<section>").addClass("detail-section").append($("<h3>").text(title)).append($content);
    }
}

/** Formatting helpers for instants. */
class Formats {
    /**
     * @param {string} isoInstant an ISO-8601 instant
     * @returns {string} the instant's date part (YYYY-MM-DD)
     */
    static date(isoInstant) {
        return isoInstant.substring(0, 10);
    }

    /**
     * @param {string} isoInstant an ISO-8601 instant
     * @returns {string} the instant reduced to minute precision (YYYY-MM-DD HH:MM)
     */
    static dateTime(isoInstant) {
        return isoInstant.substring(0, 16).replace("T", " ");
    }
}

/** Wires the views together and drives data loading. */
class App {
    constructor() {
        this._api = new ApiClient();
        this._overlay = new ReportOverlay($("#report-overlay"));
        this._listView = new ClassListView($("#class-rows"), $("#list-empty"), $("#class-count"), (classId) => this._selectClass(classId));
        this._detailView = new ClassDetailView($("#detail-pane"), (reportId) => this._openReport(reportId));
        this._$windowDays = $("#window-days");
    }

    /** Starts the application. */
    start() {
        this._$windowDays.on("change", () => this._loadClasses());
        this._loadClasses();
    }

    /** Loads and renders the class list for the selected time window. */
    _loadClasses() {
        this._api.listClasses(Number(this._$windowDays.val()))
            .then((overviews) => this._listView.render(overviews))
            .catch(() => this._listView.render([]));
    }

    /**
     * Loads and renders the details of the given class.
     * @param {number} classId the id of the selected class
     */
    _selectClass(classId) {
        this._listView.markSelected(classId);
        this._api.getClass(classId).then((detail) => this._detailView.render(detail));
    }

    /**
     * Loads and shows the given report in the overlay.
     * @param {string} reportId the id of the report to open
     */
    _openReport(reportId) {
        this._api.getReport(reportId).then((report) => this._overlay.show(report));
    }
}

$(() => new App().start());
