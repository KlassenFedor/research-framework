from __future__ import annotations

import html
import json
import os
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from research_framework.domain.errors import StorageError
from research_framework.domain.graph import Edge, GraphSnapshot, Node


@dataclass(frozen=True, slots=True)
class GraphViewNode:
    id: str
    kind: str
    status: str
    title: str
    summary: str | None
    tags: tuple[str, ...]
    aliases: tuple[str, ...]
    body: str
    details: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "status": self.status,
            "title": self.title,
            "summary": self.summary,
            "tags": list(self.tags),
            "aliases": list(self.aliases),
            "body": self.body,
            "details": dict(self.details),
        }


@dataclass(frozen=True, slots=True)
class GraphViewEdge:
    id: str
    kind: str
    source: str
    target: str
    rationale: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "source": self.source,
            "target": self.target,
            "rationale": self.rationale,
        }


@dataclass(frozen=True, slots=True)
class GraphView:
    title: str
    focus: str | None
    depth: int | None
    nodes: tuple[GraphViewNode, ...]
    edges: tuple[GraphViewEdge, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "focus": self.focus,
            "depth": self.depth,
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
        }


def _view_node(node: Node) -> GraphViewNode:
    return GraphViewNode(
        id=node.id,
        kind=node.kind.value,
        status=node.status.value,
        title=node.title,
        summary=node.summary,
        tags=node.tags,
        aliases=node.aliases,
        body=node.body,
        details=node.to_dict(),
    )


def _view_edge(edge: Edge) -> GraphViewEdge:
    return GraphViewEdge(
        id=edge.id,
        kind=edge.kind.value,
        source=edge.source,
        target=edge.target,
        rationale=edge.rationale,
    )


def build_graph_view(
    graph: GraphSnapshot,
    *,
    title: str,
    focus: str | None = None,
    depth: int | None = None,
) -> GraphView:
    """Build a deterministic full or focused view of a graph snapshot."""

    if not isinstance(title, str) or not title.strip():
        raise ValueError("title must not be blank")
    if focus is None and depth is not None:
        raise ValueError("depth requires focus")
    if depth is not None and depth < 0:
        raise ValueError("depth must not be negative")

    focus_node = graph.get_node(focus) if focus is not None else None
    effective_depth = 2 if focus_node is not None and depth is None else depth
    if focus_node is None:
        selected_nodes = graph.list_nodes()
    else:
        assert effective_depth is not None
        selected_nodes = (
            focus_node,
            *graph.traverse(focus_node.id, depth=effective_depth, direction="both"),
        )

    selected_by_id = {node.id: node for node in selected_nodes}
    selected_edges: dict[str, Edge] = {}
    for node_id in selected_by_id:
        for edge in graph.outgoing(node_id):
            if edge.target in selected_by_id:
                selected_edges[edge.id] = edge

    return GraphView(
        title=title.strip(),
        focus=focus_node.id if focus_node is not None else None,
        depth=effective_depth,
        nodes=tuple(
            _view_node(selected_by_id[node_id]) for node_id in sorted(selected_by_id)
        ),
        edges=tuple(
            _view_edge(selected_edges[edge_id]) for edge_id in sorted(selected_edges)
        ),
    )


def _json_for_html(value: Mapping[str, Any]) -> str:
    serialized = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return (
        serialized.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


_STYLE = r"""
:root {
  color-scheme: dark;
  --bg: #0b1020;
  --panel: rgba(17, 24, 39, .94);
  --panel-2: #111a2e;
  --line: #2b3852;
  --text: #e7edf8;
  --muted: #91a0b8;
  --accent: #77bdfb;
  --focus: #f8d66d;
}
* { box-sizing: border-box; }
html, body { width: 100%; height: 100%; margin: 0; overflow: hidden; }
body {
  background: radial-gradient(circle at 20% 10%, #17223d 0, var(--bg) 44%);
  color: var(--text);
  font: 14px/1.45 Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
button, input, select { font: inherit; }
button, select, input[type="search"] {
  border: 1px solid var(--line);
  border-radius: 8px;
  background: #111a2e;
  color: var(--text);
}
button { padding: 7px 11px; cursor: pointer; }
button:hover, button:focus-visible { border-color: var(--accent); outline: none; }
.app { display: grid; grid-template-rows: auto auto minmax(0, 1fr); height: 100%; }
header {
  display: flex;
  align-items: baseline;
  gap: 14px;
  padding: 14px 18px 8px;
  background: rgba(11, 16, 32, .86);
}
h1 { margin: 0; max-width: 60vw; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 18px; }
.subtitle, #counts { color: var(--muted); }
.toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px 12px;
  padding: 8px 18px 12px;
  border-bottom: 1px solid var(--line);
  background: rgba(11, 16, 32, .86);
}
.toolbar input[type="search"] { width: min(310px, 40vw); padding: 8px 10px; }
.toolbar select { padding: 7px 28px 7px 9px; }
#kind-filters { display: flex; flex-wrap: wrap; gap: 5px; }
.kind-toggle {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 5px 7px;
  border: 1px solid var(--line);
  border-radius: 999px;
  color: var(--muted);
  cursor: pointer;
  user-select: none;
}
.kind-toggle:has(input:checked) { color: var(--text); border-color: var(--kind-color); }
.kind-toggle input { accent-color: var(--kind-color); }
.tag-picker { position: relative; }
.tag-picker > summary {
  min-width: 92px;
  padding: 7px 10px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: #111a2e;
  color: var(--text);
  cursor: pointer;
  list-style: none;
  user-select: none;
}
.tag-picker > summary::-webkit-details-marker { display: none; }
.tag-picker > summary::after { content: " ▾"; color: var(--muted); }
.tag-picker[open] > summary { border-color: var(--accent); }
.tag-menu {
  position: absolute;
  z-index: 20;
  top: calc(100% + 6px);
  left: 0;
  width: min(330px, 82vw);
  padding: 10px;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: var(--panel);
  box-shadow: 0 12px 36px #0009;
}
.tag-menu-header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.tag-menu-header span { color: var(--muted); }
.tag-menu-header select { flex: 1; min-width: 90px; }
.tag-menu-header button { padding: 6px 9px; }
.tag-menu-header button:disabled { cursor: default; opacity: .45; }
#tag-filters { display: flex; flex-wrap: wrap; gap: 6px; max-height: 230px; overflow: auto; }
.tag-option {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 5px 7px;
  border: 1px solid var(--line);
  border-radius: 999px;
  color: var(--muted);
  cursor: pointer;
  user-select: none;
}
.tag-option:has(input:checked) { border-color: var(--accent); color: var(--text); background: #182743; }
.tag-option input { accent-color: var(--accent); }
.tag-count { color: var(--muted); font-size: 11px; }
.spacer { flex: 1; }
.workspace { position: relative; display: grid; grid-template-columns: minmax(0, 1fr) 340px; min-height: 0; }
.stage { position: relative; min-width: 0; overflow: hidden; }
#graph-canvas { display: block; width: 100%; height: 100%; touch-action: none; cursor: grab; }
#graph-canvas.dragging { cursor: grabbing; }
.hint {
  position: absolute;
  left: 12px;
  bottom: 10px;
  padding: 5px 8px;
  border-radius: 6px;
  background: rgba(11, 16, 32, .68);
  color: var(--muted);
  pointer-events: none;
}
#details {
  overflow: auto;
  padding: 18px;
  border-left: 1px solid var(--line);
  background: var(--panel);
}
#details h2 { margin: 0 0 4px; font-size: 18px; overflow-wrap: anywhere; }
#details h3 { margin: 18px 0 6px; font-size: 13px; color: var(--muted); text-transform: uppercase; letter-spacing: .06em; }
.badge { display: inline-block; margin: 0 5px 5px 0; padding: 2px 7px; border-radius: 999px; background: var(--panel-2); color: var(--muted); }
.node-id { margin: 3px 0 12px; color: var(--muted); font: 12px/1.4 ui-monospace, SFMono-Regular, Consolas, monospace; overflow-wrap: anywhere; }
.summary { color: #c7d2e5; }
.filter-note { margin: 10px 0; padding: 7px 9px; border-left: 3px solid var(--focus); background: #302b1d; color: #f4dda0; }
.field { margin: 8px 0; }
.field dt { color: var(--muted); }
.field dd { margin: 2px 0 0; overflow-wrap: anywhere; white-space: pre-wrap; }
.body { padding: 10px; border: 1px solid var(--line); border-radius: 8px; background: #0b1223; white-space: pre-wrap; overflow-wrap: anywhere; }
.relation { padding: 7px 0; border-bottom: 1px solid rgba(43, 56, 82, .7); }
.relation button { padding: 0; border: 0; background: transparent; color: var(--accent); text-align: left; }
.relation small { display: block; color: var(--muted); }
.empty { color: var(--muted); }
@media (max-width: 840px) {
  .workspace { grid-template-columns: minmax(0, 1fr); }
  #details { position: absolute; right: 8px; top: 8px; bottom: 8px; width: min(340px, calc(100% - 16px)); border: 1px solid var(--line); border-radius: 10px; box-shadow: 0 10px 40px #0008; }
  #details.empty-panel { display: none; }
  .hint { display: none; }
}
"""


_SCRIPT = r"""
(() => {
  "use strict";
  const data = JSON.parse(document.getElementById("graph-data").textContent);
  const canvas = document.getElementById("graph-canvas");
  const context = canvas.getContext("2d");
  const details = document.getElementById("details");
  const search = document.getElementById("search");
  const kindFilters = document.getElementById("kind-filters");
  const tagPicker = document.getElementById("tag-picker");
  const tagPickerSummary = document.getElementById("tag-picker-summary");
  const tagFilters = document.getElementById("tag-filters");
  const tagMatch = document.getElementById("tag-match");
  const clearTags = document.getElementById("clear-tags");
  const relationFilter = document.getElementById("relation-filter");
  const statusFilter = document.getElementById("status-filter");
  const counts = document.getElementById("counts");
  const showLabels = document.getElementById("show-labels");
  const colors = {
    question: "#5eb6ff", hypothesis: "#9c83ff", claim: "#cf80ff",
    experiment: "#55d5c1", run: "#45bda9", evidence: "#79d66b",
    assessment: "#f2c75c", source: "#ff9d66", artifact: "#ee7f8c",
    decision: "#f06aa6"
  };
  const nodes = data.nodes.map((node, index) => ({
    ...node, x: 0, y: 0, vx: 0, vy: 0, index, visible: true
  }));
  const byId = new Map(nodes.map(node => [node.id, node]));
  const edges = data.edges.filter(edge => byId.has(edge.source) && byId.has(edge.target));
  const selectedKinds = new Set(nodes.map(node => node.kind));
  const selectedTags = new Set();
  let selectedId = data.focus || (nodes[0] && nodes[0].id) || null;
  let scale = 1;
  let offsetX = 0;
  let offsetY = 0;
  let alpha = 1;
  let animationPending = false;
  let dragged = null;
  let panning = false;
  let pointerStart = null;
  let panStart = null;
  let pixelRatio = 1;
  let width = 1;
  let height = 1;

  function hash(value) {
    let result = 2166136261;
    for (let i = 0; i < value.length; i += 1) {
      result ^= value.charCodeAt(i);
      result = Math.imul(result, 16777619);
    }
    return result >>> 0;
  }

  const layoutKey = "rf-graph-layout-v1:" + hash(nodes.map(node => node.id).join("|"));

  function seedPositions() {
    const count = Math.max(nodes.length, 1);
    nodes.forEach((node, index) => {
      const phase = (hash(node.id) % 10000) / 10000 * Math.PI * 2;
      const ring = 100 + 52 * Math.sqrt(index + 1);
      const angle = phase + index * Math.PI * (3 - Math.sqrt(5));
      node.x = Math.cos(angle) * Math.min(ring, 80 + count * 9);
      node.y = Math.sin(angle) * Math.min(ring, 80 + count * 9);
      node.vx = 0;
      node.vy = 0;
    });
  }

  function loadPositions() {
    seedPositions();
    try {
      const saved = JSON.parse(localStorage.getItem(layoutKey) || "null");
      if (!saved || typeof saved !== "object") return;
      nodes.forEach(node => {
        const point = saved[node.id];
        if (Array.isArray(point) && Number.isFinite(point[0]) && Number.isFinite(point[1])) {
          node.x = point[0];
          node.y = point[1];
        }
      });
    } catch (_) {
      // Storage can be unavailable for local files; visualization still works.
    }
  }

  function savePositions() {
    try {
      const saved = Object.fromEntries(nodes.map(node => [node.id, [node.x, node.y]]));
      localStorage.setItem(layoutKey, JSON.stringify(saved));
    } catch (_) {
      // Ignore browser privacy/quota restrictions.
    }
  }

  function visibleNodes() {
    return nodes.filter(node => node.visible);
  }

  function visibleEdges() {
    const relation = relationFilter.value;
    return edges.filter(edge => {
      const source = byId.get(edge.source);
      const target = byId.get(edge.target);
      return source.visible && target.visible && (relation === "all" || edge.kind === relation);
    });
  }

  function applyFilters() {
    const query = search.value.trim().toLocaleLowerCase();
    const status = statusFilter.value;
    const tags = [...selectedTags];
    nodes.forEach(node => {
      const haystack = [node.id, node.title, node.summary || "", ...node.tags, ...node.aliases]
        .join(" ").toLocaleLowerCase();
      const matchesTags = !tags.length || (tagMatch.value === "all"
        ? tags.every(tag => node.tags.includes(tag))
        : tags.some(tag => node.tags.includes(tag)));
      node.visible = selectedKinds.has(node.kind)
        && (status === "all" || node.status === status)
        && matchesTags
        && (!query || haystack.includes(query));
    });
    const shownNodes = visibleNodes().length;
    const shownEdges = visibleEdges().length;
    counts.textContent = `${shownNodes} nodes · ${shownEdges} relations`;
    tagPickerSummary.textContent = tags.length
      ? `tags: ${tags.length} (${tagMatch.value})`
      : "tags: all";
    tagMatch.disabled = tags.length < 2;
    clearTags.disabled = !tags.length;
    renderDetails();
    schedule();
  }

  function addOption(select, value, label) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label;
    select.append(option);
  }

  function buildControls() {
    [...new Set(nodes.map(node => node.kind))].sort().forEach(kind => {
      const label = document.createElement("label");
      label.className = "kind-toggle";
      label.style.setProperty("--kind-color", colors[kind] || "#a9b5c8");
      const input = document.createElement("input");
      input.type = "checkbox";
      input.checked = true;
      input.addEventListener("change", () => {
        if (input.checked) selectedKinds.add(kind); else selectedKinds.delete(kind);
        applyFilters();
      });
      const text = document.createElement("span");
      text.textContent = kind;
      label.append(input, text);
      kindFilters.append(label);
    });

    const tagCounts = new Map();
    nodes.forEach(node => node.tags.forEach(tag => {
      tagCounts.set(tag, (tagCounts.get(tag) || 0) + 1);
    }));
    [...tagCounts].sort(([left], [right]) => left.localeCompare(right))
      .forEach(([tag, count]) => {
        const label = document.createElement("label");
        label.className = "tag-option";
        const input = document.createElement("input");
        input.type = "checkbox";
        input.value = tag;
        input.addEventListener("change", () => {
          if (input.checked) selectedTags.add(tag); else selectedTags.delete(tag);
          applyFilters();
        });
        const text = document.createElement("span");
        text.textContent = tag;
        const amount = document.createElement("span");
        amount.className = "tag-count";
        amount.textContent = String(count);
        label.append(input, text, amount);
        tagFilters.append(label);
      });
    tagPicker.hidden = tagCounts.size === 0;

    [...new Set(edges.map(edge => edge.kind))].sort()
      .forEach(kind => addOption(relationFilter, kind, kind));
    [...new Set(nodes.map(node => node.status))].sort()
      .forEach(status => addOption(statusFilter, status, status));
  }

  function resize() {
    const rect = canvas.getBoundingClientRect();
    pixelRatio = Math.max(1, window.devicePixelRatio || 1);
    width = Math.max(1, rect.width);
    height = Math.max(1, rect.height);
    canvas.width = Math.round(width * pixelRatio);
    canvas.height = Math.round(height * pixelRatio);
    schedule();
  }

  function screen(node) {
    return { x: node.x * scale + offsetX, y: node.y * scale + offsetY };
  }

  function fit() {
    const visible = visibleNodes();
    if (!visible.length) {
      scale = 1;
      offsetX = width / 2;
      offsetY = height / 2;
      schedule();
      return;
    }
    const xs = visible.map(node => node.x);
    const ys = visible.map(node => node.y);
    const minX = Math.min(...xs) - 60;
    const maxX = Math.max(...xs) + 60;
    const minY = Math.min(...ys) - 60;
    const maxY = Math.max(...ys) + 60;
    scale = Math.max(.08, Math.min(2.4, Math.min(width / (maxX - minX), height / (maxY - minY))));
    offsetX = width / 2 - (minX + maxX) / 2 * scale;
    offsetY = height / 2 - (minY + maxY) / 2 * scale;
    schedule();
  }

  function simulate() {
    const activeNodes = visibleNodes();
    const activeEdges = visibleEdges();
    activeEdges.forEach(edge => {
      const source = byId.get(edge.source);
      const target = byId.get(edge.target);
      const dx = target.x - source.x;
      const dy = target.y - source.y;
      const distance = Math.max(1, Math.hypot(dx, dy));
      const force = (distance - 150) * .0017 * alpha;
      const fx = dx / distance * force;
      const fy = dy / distance * force;
      source.vx += fx; source.vy += fy;
      target.vx -= fx; target.vy -= fy;
    });

    const cellSize = 92;
    const buckets = new Map();
    activeNodes.forEach(node => {
      const key = `${Math.floor(node.x / cellSize)},${Math.floor(node.y / cellSize)}`;
      if (!buckets.has(key)) buckets.set(key, []);
      buckets.get(key).push(node);
    });
    activeNodes.forEach(node => {
      const cellX = Math.floor(node.x / cellSize);
      const cellY = Math.floor(node.y / cellSize);
      for (let ox = -1; ox <= 1; ox += 1) {
        for (let oy = -1; oy <= 1; oy += 1) {
          const neighbors = buckets.get(`${cellX + ox},${cellY + oy}`) || [];
          neighbors.forEach(other => {
            if (other.index <= node.index) return;
            let dx = other.x - node.x;
            let dy = other.y - node.y;
            let distance = Math.hypot(dx, dy);
            if (distance < .1) { dx = .1; dy = 0; distance = .1; }
            if (distance >= 78) return;
            const force = (78 - distance) * .004 * alpha;
            const fx = dx / distance * force;
            const fy = dy / distance * force;
            node.vx -= fx; node.vy -= fy;
            other.vx += fx; other.vy += fy;
          });
        }
      }
      node.vx += -node.x * .000025 * alpha;
      node.vy += -node.y * .000025 * alpha;
    });
    activeNodes.forEach(node => {
      if (dragged === node) return;
      node.vx *= .88;
      node.vy *= .88;
      node.x += node.vx;
      node.y += node.vy;
    });
    alpha *= .984;
  }

  function drawArrow(source, target, color) {
    const dx = target.x - source.x;
    const dy = target.y - source.y;
    const distance = Math.max(1, Math.hypot(dx, dy));
    const ux = dx / distance;
    const uy = dy / distance;
    const nodeRadius = 12;
    const startX = source.x + ux * nodeRadius;
    const startY = source.y + uy * nodeRadius;
    const endX = target.x - ux * (nodeRadius + 3);
    const endY = target.y - uy * (nodeRadius + 3);
    context.beginPath();
    context.moveTo(startX, startY);
    context.lineTo(endX, endY);
    context.strokeStyle = color;
    context.lineWidth = 1.15;
    context.stroke();
    context.beginPath();
    context.moveTo(endX, endY);
    context.lineTo(endX - ux * 8 - uy * 4, endY - uy * 8 + ux * 4);
    context.lineTo(endX - ux * 8 + uy * 4, endY - uy * 8 - ux * 4);
    context.closePath();
    context.fillStyle = color;
    context.fill();
  }

  function draw() {
    context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
    context.clearRect(0, 0, width, height);
    const activeEdges = visibleEdges();
    activeEdges.forEach(edge => {
      const source = screen(byId.get(edge.source));
      const target = screen(byId.get(edge.target));
      drawArrow(source, target, "rgba(139, 156, 184, .48)");
      if (showLabels.checked && scale > .42) {
        context.font = "11px ui-monospace, SFMono-Regular, Consolas, monospace";
        context.textAlign = "center";
        context.textBaseline = "bottom";
        context.fillStyle = "rgba(187, 200, 221, .85)";
        context.fillText(edge.kind, (source.x + target.x) / 2, (source.y + target.y) / 2 - 3);
      }
    });
    visibleNodes().forEach(node => {
      const point = screen(node);
      const radius = node.id === selectedId ? 14 : 11;
      context.beginPath();
      context.arc(point.x, point.y, radius, 0, Math.PI * 2);
      context.fillStyle = colors[node.kind] || "#a9b5c8";
      context.fill();
      context.lineWidth = node.id === data.focus ? 3 : (node.id === selectedId ? 2 : 1);
      context.strokeStyle = node.id === data.focus ? "#f8d66d" : (node.id === selectedId ? "#ffffff" : "rgba(5, 10, 20, .8)");
      context.stroke();
      if (scale > .48 || node.id === selectedId || node.id === data.focus) {
        context.font = node.id === selectedId
          ? "600 12px Inter, system-ui, sans-serif"
          : "12px Inter, system-ui, sans-serif";
        context.textAlign = "center";
        context.textBaseline = "top";
        context.fillStyle = "#e7edf8";
        const label = node.title.length > 38 ? `${node.title.slice(0, 36)}…` : node.title;
        context.fillText(label, point.x, point.y + radius + 5);
      }
    });
  }

  function frame() {
    animationPending = false;
    if (alpha > .006 && !panning) simulate();
    draw();
    if (alpha > .006 || dragged) schedule();
  }

  function schedule() {
    if (animationPending) return;
    animationPending = true;
    requestAnimationFrame(frame);
  }

  function pointerPosition(event) {
    const rect = canvas.getBoundingClientRect();
    return { x: event.clientX - rect.left, y: event.clientY - rect.top };
  }

  function hitNode(point) {
    let hit = null;
    let best = 20;
    visibleNodes().forEach(node => {
      const location = screen(node);
      const distance = Math.hypot(location.x - point.x, location.y - point.y);
      if (distance < best) { best = distance; hit = node; }
    });
    return hit;
  }

  function appendText(parent, tag, value, className) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    element.textContent = value;
    parent.append(element);
    return element;
  }

  function displayValue(value) {
    if (value === null || value === undefined) return "";
    if (typeof value === "object") return JSON.stringify(value, null, 2);
    return String(value);
  }

  function selectNode(nodeId) {
    if (!byId.has(nodeId)) return;
    selectedId = nodeId;
    renderDetails();
    schedule();
  }

  function renderDetails() {
    details.replaceChildren();
    const node = selectedId && byId.get(selectedId);
    if (!node) {
      details.classList.add("empty-panel");
      appendText(details, "p", "Select a node to inspect its metadata and relations.", "empty");
      return;
    }
    details.classList.remove("empty-panel");
    appendText(details, "h2", node.title);
    appendText(details, "div", node.id, "node-id");
    [node.kind, node.status, ...node.tags].forEach(value => appendText(details, "span", value, "badge"));
    if (!node.visible) {
      appendText(details, "p", "Hidden by current filters · details remain available", "filter-note");
    }
    if (node.summary) appendText(details, "p", node.summary, "summary");

    const ignored = new Set(["format_version", "id", "kind", "title", "status", "summary", "tags", "aliases"]);
    const entries = Object.entries(node.details).filter(([key]) => !ignored.has(key));
    if (entries.length) {
      appendText(details, "h3", "Metadata");
      const list = document.createElement("dl");
      entries.forEach(([key, value]) => {
        const wrapper = document.createElement("div");
        wrapper.className = "field";
        appendText(wrapper, "dt", key);
        appendText(wrapper, "dd", displayValue(value));
        list.append(wrapper);
      });
      details.append(list);
    }
    if (node.body.trim()) {
      appendText(details, "h3", "Body");
      appendText(details, "div", node.body.trim(), "body");
    }

    const adjacent = edges.filter(edge => edge.source === node.id || edge.target === node.id);
    appendText(details, "h3", `Relations (${adjacent.length})`);
    if (!adjacent.length) appendText(details, "p", "No adjacent relations.", "empty");
    adjacent.forEach(edge => {
      const outgoing = edge.source === node.id;
      const neighborId = outgoing ? edge.target : edge.source;
      const neighbor = byId.get(neighborId);
      const row = document.createElement("div");
      row.className = "relation";
      const button = document.createElement("button");
      button.type = "button";
      const hidden = neighbor && !neighbor.visible ? " (hidden)" : "";
      button.textContent = `${outgoing ? "→" : "←"} ${edge.kind}: ${neighbor ? neighbor.title : neighborId}${hidden}`;
      button.addEventListener("click", () => selectNode(neighborId));
      row.append(button);
      if (edge.rationale) appendText(row, "small", edge.rationale);
      details.append(row);
    });
  }

  canvas.addEventListener("pointerdown", event => {
    const point = pointerPosition(event);
    const node = hitNode(point);
    pointerStart = point;
    canvas.setPointerCapture(event.pointerId);
    canvas.classList.add("dragging");
    if (node) {
      dragged = node;
      selectNode(node.id);
      alpha = Math.max(alpha, .12);
    } else {
      panning = true;
      panStart = { x: offsetX, y: offsetY };
    }
  });

  canvas.addEventListener("pointermove", event => {
    if (!pointerStart) return;
    const point = pointerPosition(event);
    if (dragged) {
      dragged.x = (point.x - offsetX) / scale;
      dragged.y = (point.y - offsetY) / scale;
      dragged.vx = 0; dragged.vy = 0;
    } else if (panning) {
      offsetX = panStart.x + point.x - pointerStart.x;
      offsetY = panStart.y + point.y - pointerStart.y;
    }
    schedule();
  });

  function endPointer(event) {
    if (canvas.hasPointerCapture(event.pointerId)) canvas.releasePointerCapture(event.pointerId);
    if (dragged) savePositions();
    dragged = null;
    panning = false;
    pointerStart = null;
    canvas.classList.remove("dragging");
    schedule();
  }
  canvas.addEventListener("pointerup", endPointer);
  canvas.addEventListener("pointercancel", endPointer);

  canvas.addEventListener("wheel", event => {
    event.preventDefault();
    const point = pointerPosition(event);
    const worldX = (point.x - offsetX) / scale;
    const worldY = (point.y - offsetY) / scale;
    const factor = Math.exp(-event.deltaY * .0012);
    scale = Math.max(.08, Math.min(5, scale * factor));
    offsetX = point.x - worldX * scale;
    offsetY = point.y - worldY * scale;
    schedule();
  }, { passive: false });

  search.addEventListener("input", applyFilters);
  relationFilter.addEventListener("change", applyFilters);
  statusFilter.addEventListener("change", applyFilters);
  tagMatch.addEventListener("change", applyFilters);
  clearTags.addEventListener("click", () => {
    selectedTags.clear();
    tagFilters.querySelectorAll('input[type="checkbox"]')
      .forEach(input => { input.checked = false; });
    applyFilters();
  });
  showLabels.addEventListener("change", schedule);
  document.getElementById("fit").addEventListener("click", fit);
  document.getElementById("reset-layout").addEventListener("click", () => {
    try { localStorage.removeItem(layoutKey); } catch (_) { /* ignored */ }
    seedPositions();
    alpha = 1;
    fit();
    schedule();
  });
  window.addEventListener("resize", resize);
  document.addEventListener("click", event => {
    if (tagPicker.open && !tagPicker.contains(event.target)) tagPicker.open = false;
  });
  document.addEventListener("keydown", event => {
    if (event.key === "Escape") tagPicker.open = false;
  });

  loadPositions();
  buildControls();
  resize();
  applyFilters();
  fit();
  renderDetails();
  schedule();
})();
"""


def render_graph_html(view: GraphView) -> str:
    """Render a standalone, deterministic and safely embedded graph document."""

    title = html.escape(view.title, quote=True)
    focus_note = (
        f"Local view · depth {view.depth}" if view.focus is not None else "Full graph"
    )
    payload = _json_for_html(view.to_dict())
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="dark">
  <title>{title} · Research graph</title>
  <style>{_STYLE}</style>
</head>
<body>
  <div class="app">
    <header>
      <h1>{title}</h1>
      <span class="subtitle">{focus_note}</span>
      <span id="counts"></span>
    </header>
    <div class="toolbar" aria-label="Graph controls">
      <input id="search" type="search" placeholder="Search title, ID, tag or alias" aria-label="Search nodes">
      <div id="kind-filters" aria-label="Node kind filters"></div>
      <details class="tag-picker" id="tag-picker">
        <summary id="tag-picker-summary">tags: all</summary>
        <div class="tag-menu">
          <div class="tag-menu-header">
            <span>Match</span>
            <select id="tag-match" aria-label="Tag matching mode">
              <option value="any">any selected tag</option>
              <option value="all">all selected tags</option>
            </select>
            <button id="clear-tags" type="button">Clear</button>
          </div>
          <div id="tag-filters" aria-label="Tag filters"></div>
        </div>
      </details>
      <select id="status-filter" aria-label="Filter node status"><option value="all">all statuses</option></select>
      <select id="relation-filter" aria-label="Filter relation kind"><option value="all">all relations</option></select>
      <label><input id="show-labels" type="checkbox" checked> relation labels</label>
      <span class="spacer"></span>
      <button id="fit" type="button">Fit</button>
      <button id="reset-layout" type="button">Reset layout</button>
    </div>
    <main class="workspace">
      <section class="stage" aria-label="Interactive research graph">
        <canvas id="graph-canvas"></canvas>
        <div class="hint">Drag nodes · drag background to pan · scroll to zoom</div>
      </section>
      <aside id="details" aria-live="polite"></aside>
    </main>
  </div>
  <script type="application/json" id="graph-data">{payload}</script>
  <script>{_SCRIPT}</script>
</body>
</html>
"""


def write_graph_html(path: Path, document: str) -> None:
    """Atomically write a rendered graph document."""

    temporary: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        )
        temporary = Path(temporary_name)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
            stream.write(document)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    except OSError as error:
        raise StorageError(f"cannot write graph HTML {path}: {error}") from error
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
