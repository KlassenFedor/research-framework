# Research Framework

Git-native, text-first research graph with Markdown/YAML storage, an immutable
in-memory graph, validation, a public Python API and the `rf` CLI.

- Architecture: [`docs/architecture.md`](docs/architecture.md)
- Testing contract: [`docs/testing.md`](docs/testing.md)

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
```
