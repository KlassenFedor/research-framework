# Benchmark harness

Reproducible performance measurements for large graphs. Nothing here is imported
by the framework; it exists so that a performance claim can be re-checked instead
of remembered.

```bash
# Generate a synthetic but fully valid vault.
uv run python bench/generate.py /tmp/vaults/v10k 10010

# Run every operation against it and write bench/results/<name>.json.
uv run python bench/run.py /tmp/vaults/v10k

# Break the cold path into phases (read, YAML decode, validation, format).
uv run python bench/phases.py /tmp/vaults/v10k
```

`generate.py` writes one repeating unit of eleven Nodes covering all ten kinds
with sixteen outgoing relations plus one cross-unit edge, so the graph is
connected and the relation density (~1.55 per Node) is realistic. The generated
vault passes `rf validate` and `rf format --check` without diagnostics: the
benchmark measures complete work, not an early exit.

Absolute timings depend on the machine, the filesystem and the page cache. Treat
the per-Node costs and the ratios between operations as the durable result, and
re-measure on an idle machine before comparing runs.
