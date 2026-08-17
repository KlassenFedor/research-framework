# Research Framework

Git-native, text-first research graph with Markdown/YAML storage, an immutable
in-memory graph, validation, a public Python API and the `rf` CLI.

- Architecture: [`docs/architecture.md`](docs/architecture.md)
- Testing contract: [`docs/testing.md`](docs/testing.md)

Versioned JSON Schema Draft 2020-12 contracts are bundled with the package and
available through `research_framework.node_schema()` and `project_schema()`.

## Development

Requires Python 3.11+ and [`uv`](https://docs.astral.sh/uv/).

```bash
uv sync
uv run pytest
```

Run the complete contract suite:

```bash
uv run pytest
uv run ruff check src tests
uv run ruff format --check src tests
```

Create and inspect a project:

```bash
uv run rf init ./example --title "Example research"
cd example
uv run rf validate
uv run rf format --check
# Apply canonical YAML front matter formatting when the check reports drift:
uv run rf format
```
