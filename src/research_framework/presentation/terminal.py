from __future__ import annotations

import json
from collections.abc import Iterable, Sequence

from research_framework.domain.graph import Edge, GraphSnapshot, Node


def _text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple, set, frozenset)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return str(value)


def _table(headers: Sequence[str], rows: Iterable[Sequence[object]]) -> str:
    values = [[_text(cell) for cell in row] for row in rows]
    widths = [len(header) for header in headers]
    for row in values:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))

    def line(row: Sequence[str]) -> str:
        return "  ".join(
            cell.ljust(widths[index]) for index, cell in enumerate(row)
        ).rstrip()

    header = line(headers)
    separator = line(tuple("-" * width for width in widths))
    return "\n".join((header, separator, *(line(row) for row in values)))


def render_node(node: Node) -> str:
    lines = [
        f"ID:       {node.id}",
        f"Kind:     {node.kind.value}",
        f"Status:   {node.status.value}",
        f"Title:    {node.title}",
    ]
    if node.summary is not None:
        lines.append(f"Summary:  {node.summary}")
    if node.tags:
        lines.append(f"Tags:     {', '.join(node.tags)}")
    if node.aliases:
        lines.append(f"Aliases:  {', '.join(node.aliases)}")
    for field, value in node.data.items():
        label = field.replace("_", " ").title()
        lines.append(f"{label}: {_text(value)}")
    lines.extend(
        (
            f"Created:  {node.created_at.isoformat()} by {node.created_by.id}",
            f"Updated:  {node.updated_at.isoformat()} by {node.updated_by.id}",
            f"Revision: {node.revision}",
            f"Path:     {node.path}",
            "",
            "Body:",
            node.body.strip() or "(empty)",
        )
    )
    return "\n".join(lines)


def render_nodes(nodes: Sequence[Node]) -> str:
    return _table(
        ("ID", "KIND", "STATUS", "TITLE"),
        ((node.id, node.kind.value, node.status.value, node.title) for node in nodes),
    )


def render_edges(edges: Sequence[Edge]) -> str:
    return _table(
        ("ID", "KIND", "SOURCE", "TARGET", "RATIONALE"),
        (
            (edge.id, edge.kind.value, edge.source, edge.target, edge.rationale)
            for edge in edges
        ),
    )


def render_neighborhood(
    graph: GraphSnapshot,
    center: Node,
    edges: Sequence[Edge],
) -> str:
    lines = [f"{center.id} [{center.kind.value}] {center.title}"]
    for edge in edges:
        outgoing = edge.source == center.id
        neighbor_id = edge.target if outgoing else edge.source
        neighbor = graph.get_node(neighbor_id)
        direction = "→" if outgoing else "←"
        lines.append(
            f"  {direction} {edge.kind.value} {neighbor.id} "
            f"[{neighbor.kind.value}] {neighbor.title}"
        )
    if not edges:
        lines.append("  (no adjacent relations)")
    return "\n".join(lines)


def render_path(
    graph: GraphSnapshot,
    source: str,
    edges: Sequence[Edge] | None,
) -> str:
    start = graph.get_node(source)
    if edges is None:
        return f"No path from {start.id}"
    lines = [f"{start.id} [{start.kind.value}] {start.title}"]
    for edge in edges:
        target = graph.get_node(edge.target)
        lines.append(
            f"  └─ {edge.kind.value} → {target.id} [{target.kind.value}] {target.title}"
        )
    return "\n".join(lines)
