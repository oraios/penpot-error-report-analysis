# Penpot Error Report Analysis

A platform for the systematic, LLM-driven analysis of Penpot error reports.

Error reports (retrieved from the Penpot RPC API) are grouped into equivalence classes via a
versioned fingerprint algorithm. An LLM, connected through the bundled MCP server, analyzes
representative members of unanalyzed classes and stores markdown insights in a local database.
Humans review the results through a web dashboard.

## Components

* `src/error_analysis/reports` — report source client and typed report model
* `src/error_analysis/fingerprint` — versioned fingerprint algorithms
* `src/error_analysis/persistence` — SQLAlchemy model and repository abstractions
* `src/error_analysis/classify` — classification workflow
* `src/error_analysis/mcp` — MCP server exposing the analysis workflow to LLMs
* `src/error_analysis/web` — Flask backend and jQuery dashboard

## Setup

Requires [pixi](https://pixi.sh). Install the environment with:

    pixi install

Configuration is read from the Penpot repository root `.env` file
(`PENPOT_API_URI`, `PENPOT_ACCESS_TOKEN` with `error-reports:read` permission).

## Usage

### MCP server (LLM interface)

For clients that spawn the server locally, register it with stdio transport:

    pixi run --manifest-path /home/penpot/penpot/error-report-analysis/pyproject.toml error-analysis-mcp

For clients that connect via URL, run it with HTTP transport instead and register the URL
`http://127.0.0.1:5101/mcp`:

    pixi run error-analysis-mcp --transport streamable-http [--host 127.0.0.1] [--port 5101]

An analysis session is started by calling the `bootstrap_analysis` tool: it classifies recent reports
and returns an overview of the top unanalyzed classes, which the LLM presents to the user, who decides
how many (or which) classes shall be analyzed. The chosen classes are then retrieved in full detail via
`get_analysis_candidates`, which also delivers the analysis workflow instructions. The analyzing LLM
should additionally have access to the Penpot development environment (code analysis tools) for
root-cause investigation.

### Classification backfills

Reports are classified incrementally (each report's details are retrieved once). For large windows
over high-volume deployments, perform the initial classification via the command line rather than
through the MCP tool:

    pixi run error-analysis-classify --days 30 [--concurrency 8]

Subsequent `bootstrap_analysis` calls then only classify reports that arrived since.

### Web dashboard

    pixi run error-analysis-web

serves the dashboard at http://127.0.0.1:5100 (port configurable via `ERROR_ANALYSIS_WEB_PORT`).
The dashboard lists the equivalence classes of a selectable time window and provides per-class
fingerprint signatures, analysis insights, and member report inspection.

## Development

    pixi run check   # format, lint, typecheck

See `CONVENTIONS.md` for binding code style and design conventions.
