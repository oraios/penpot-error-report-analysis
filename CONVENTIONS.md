# Code Style & Conventions

These conventions are binding for all code in this repository.

## Language & Tooling

* Python 3.13; dependencies and environments are managed with **pixi**.
* Static typing is mandatory: every public function, method, and attribute is fully type-annotated;
  `ty check` must pass.
* `ruff` is used for linting and formatting (line length 140).
* All tool configuration lives in `pyproject.toml`/`pixi.toml`; no per-developer overrides.

## Design

The codebase uses an idiomatic, object-oriented style: Java-esque principles expressed through
Pythonic syntax and constructs.

* Each concern has exactly one home.
  A mechanism whose parts are only correct in combination is implemented as a single
  component/class, and its parts are private to it; the public surface is minimal.
  Java-like encapsulation: helper functions and constants used by only one abstraction are
  internal to the respective class (underscore-prefixed methods/attributes, or nested privately).
* Invariants are enforced through structure and visibility; interfaces must not permit states
  the design forbids. Prefer constructors/factories that establish validity over mutable
  post-hoc configuration; prefer frozen dataclasses for value objects.
* Non-trivial interfaces are expressed as explicitly typed abstractions rather than mere
  functions: use abstract base classes and the strategy pattern (e.g. a `FingerprintAlgorithm`
  ABC rather than a `Callable[[Report], str]`).
* Low-level data structures (dicts, tuples, primitive soup) are avoided wherever an
  object-oriented abstraction is more appropriate. Simple data records are `@dataclass`es,
  never dictionaries or tuples. Closed sets of values are `Enum`s, never string constants.
* Dependencies flow inward: domain logic (reports, fingerprinting, persistence model) does not
  import from delivery layers (web, MCP). Delivery layers are thin adapters.
* No module-level executable code apart from definitions; entry points are explicit
  (`main()` functions wired via scripts).

## Naming

* Modules: short, lower_snake_case, named for the concern they own.
* Classes: nouns or noun phrases (`ReportRepository`, `EquivalenceClass`);
  ABCs are named for the abstraction, not suffixed with `Interface` or `Abstract`
  (implementations carry the qualifier: `SqliteReportRepository`).
* Methods: verbs or verb phrases; queries are nouns/`get_*`, commands are imperative verbs.
* Private members are underscore-prefixed; there is no access to another object's
  underscore-prefixed members from outside.

## Testing

* No automated tests are written for the time being (deliberate project decision).
* Should tests be introduced later: they cover externally observable behavior and guarantees,
  never implementation structure.

## Docstrings & Comments

* reStructuredText is used consistently (`:param name:`, `:return:`, `:raises Exc:`).
* Function implementations are structured into functional blocks separated by blank lines.
  Atop each functional block stands an elliptical phrase (starting with a lower-case letter)
  concisely describing the purpose of the block.
* Descriptions of parameters, methods/functions, and classes use a precise style: the initial
  (elliptical) phrase clearly defines *what* the element is; any details follow in subsequent
  sentences.
* Each piece of information appears exactly once, at the element that owns it: callers do not
  explain callees' internals, and callees do not describe their callers.

### Example

```python
class ReportClassifier:
    """
    Assigns error reports to equivalence classes based on a fingerprint algorithm.

    Classes are created on demand; the algorithm version is recorded with each class,
    enabling later re-fingerprinting.
    """

    def classify(self, report: ErrorReport) -> EquivalenceClass:
        """
        Determines the equivalence class of the given report, creating the class if it
        does not yet exist, and persists the association.

        :param report: the report to classify
        :return: the equivalence class the report was assigned to
        """
        # compute the versioned fingerprint for the report
        fingerprint = self._algorithm.fingerprint(report)

        # resolve or create the corresponding equivalence class
        eq_class = self._repository.find_class(fingerprint) or self._create_class(fingerprint)

        # record the association
        self._repository.add_association(report.id, eq_class.id)
        return eq_class
```

## Errors & Logging

* Failures raise exceptions; error state is never encoded in return values
  (no `None`-on-error, no status tuples). Domain-specific exception types where callers
  are expected to discriminate.
* Logging uses the stdlib `logging` module with module-level loggers
  (`log = logging.getLogger(__name__)`); no `print` outside CLI entry points.

## Repository Layout

```
error-report-analysis/
  pixi.toml / pyproject.toml
  CONVENTIONS.md
  src/error_analysis/
    reports/        # report source client and typed report model
    fingerprint/    # fingerprint algorithms (versioned)
    persistence/    # SQLAlchemy model + repository abstractions
    classify/       # classification workflow
    mcp/            # MCP server (delivery layer)
    web/            # Flask app: JSON endpoints + static dashboard (delivery layer)
      static/       # jQuery dashboard (object-oriented JS)
```

## Dashboard JavaScript

* Object-oriented design: ES6 classes encapsulating state and DOM interaction; no free-floating
  jQuery spaghetti. One class per view concern (e.g. `ClassListView`, `InsightPanel`).
* The dashboard consumes only the documented JSON endpoints; no scraping of server-rendered HTML.
