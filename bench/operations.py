"""Run one benchmark operation in a fresh process and report time and peak RSS."""

from __future__ import annotations

import json
import resource
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

VAULT = Path(sys.argv[1])
OP = sys.argv[2]
COLD = "--cold" in sys.argv[3:]

if COLD:
    import shutil

    shutil.rmtree(VAULT / ".research-cache", ignore_errors=True)


def peak_rss_mib() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def run() -> dict[str, object]:
    from research_framework import Actor, ActorKind, ClaimDraft, Project
    from research_framework.storage.discovery import (
        discover_node_files,
        discover_project,
    )
    from research_framework.storage.loader import load_snapshot
    from research_framework.validation import (
        validate_and_load_snapshot,
        validate_project,
    )

    extra: dict[str, object] = {}

    if OP == "discover":
        start = time.perf_counter()
        project = discover_project(VAULT)
        paths = discover_node_files(project)
        elapsed = time.perf_counter() - start
        extra["files"] = len(paths)

    elif OP == "load_snapshot":
        project = discover_project(VAULT)
        start = time.perf_counter()
        snapshot = load_snapshot(project)
        elapsed = time.perf_counter() - start
        extra["nodes"] = len(snapshot.list_nodes())

    elif OP == "validate_project":
        start = time.perf_counter()
        diagnostics = validate_project(VAULT)
        elapsed = time.perf_counter() - start
        extra["diagnostics"] = len(diagnostics)

    elif OP == "validate_and_load":
        project = discover_project(VAULT)
        start = time.perf_counter()
        diagnostics, snapshot = validate_and_load_snapshot(project)
        elapsed = time.perf_counter() - start
        extra["diagnostics"] = len(diagnostics)

    elif OP == "open":
        start = time.perf_counter()
        Project.open(VAULT)
        elapsed = time.perf_counter() - start

    elif OP == "get_node":
        project = Project.open(VAULT)
        snapshot = project.snapshot()
        start = time.perf_counter()
        for _ in range(100):
            snapshot.get_node("hyp-1")
        elapsed = (time.perf_counter() - start) / 100

    elif OP == "list_nodes":
        project = Project.open(VAULT)
        snapshot = project.snapshot()
        start = time.perf_counter()
        nodes = snapshot.list_nodes()
        elapsed = time.perf_counter() - start
        extra["nodes"] = len(nodes)

    elif OP == "traverse":
        project = Project.open(VAULT)
        snapshot = project.snapshot()
        start = time.perf_counter()
        reached = snapshot.traverse("hyp-1", depth=3)
        elapsed = time.perf_counter() - start
        extra["reached"] = len(list(reached))

    elif OP == "export_json":
        project = Project.open(VAULT)
        snapshot = project.snapshot()
        start = time.perf_counter()
        payload = snapshot.export_json()
        elapsed = time.perf_counter() - start
        extra["bytes"] = len(payload)

    elif OP == "format_check":
        project = Project.open(VAULT)
        start = time.perf_counter()
        result = project.format(check=True)
        elapsed = time.perf_counter() - start
        extra["checked"] = result.checked_files

    elif OP == "create_node":
        project = Project.open(VAULT)
        actor = Actor(kind=ActorKind.HUMAN, id="bench")
        samples = []
        created = []
        for index in range(10):
            start = time.perf_counter()
            node = project.create_node(
                ClaimDraft(
                    title=f"Bench claim {index}",
                    statement="Bench statement.",
                ),
                actor=actor,
            )
            samples.append(time.perf_counter() - start)
            created.append(node.path)
        elapsed = sum(samples) / len(samples)
        extra["first"] = samples[0]
        extra["last"] = samples[-1]
        for path in created:
            path.unlink(missing_ok=True)

    elif OP == "update_node":
        project = Project.open(VAULT)
        actor = Actor(kind=ActorKind.HUMAN, id="bench")
        samples = []
        for index in range(10):
            start = time.perf_counter()
            node = project.snapshot().get_node("hyp-1")
            project.update_node(
                node.id,
                patch={"summary": f"Updated by benchmark {index}."},
                expected_revision=node.revision,
                actor=actor,
            )
            samples.append(time.perf_counter() - start)
        elapsed = sum(samples) / len(samples)
        extra["first"] = samples[0]
        extra["last"] = samples[-1]

    elif OP == "render_html":
        from research_framework.presentation.html_graph import (
            build_graph_view,
            render_graph_html,
        )

        project = Project.open(VAULT)
        snapshot = project.snapshot()
        start = time.perf_counter()
        html = render_graph_html(build_graph_view(snapshot, title="Bench"))
        elapsed = time.perf_counter() - start
        extra["bytes"] = len(html)

    else:
        raise SystemExit(f"unknown op: {OP}")

    return {"op": OP, "seconds": elapsed, "peak_rss_mib": peak_rss_mib(), **extra}


if __name__ == "__main__":
    print(json.dumps(run()))
