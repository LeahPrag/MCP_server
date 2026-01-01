# src/analysis/graph_viz.py
from __future__ import annotations

from collections import deque
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple


DEFAULT_EDGE_TYPES: Set[str] = {"call"}


def _label_from_id(node_id: str) -> str:
    if ":" in node_id:
        prefix, rest = node_id.split(":", 1)
        if prefix in {"func", "class", "file"}:
            return rest
    return node_id


def _iter_edges(graph: Dict[str, Any], edge_types: Set[str]) -> Iterable[Tuple[str, str]]:
    for e in graph.get("edges", []):
        if not isinstance(e, dict):
            continue
        if edge_types and e.get("type") not in edge_types:
            continue
        s = e.get("source")
        t = e.get("target")
        if isinstance(s, str) and isinstance(t, str):
            yield s, t


def _build_adj(graph: Dict[str, Any], edge_types: Set[str]) -> Dict[str, List[str]]:
    adj: Dict[str, List[str]] = {}
    for s, t in _iter_edges(graph, edge_types):
        adj.setdefault(s, []).append(t)
    return adj


def _build_rev(graph: Dict[str, Any], edge_types: Set[str]) -> Dict[str, List[str]]:
    rev: Dict[str, List[str]] = {}
    for s, t in _iter_edges(graph, edge_types):
        rev.setdefault(t, []).append(s)
    return rev


def _collect_subgraph(
    graph: Dict[str, Any],
    focus: Optional[str],
    direction: str,
    depth: int,
    edge_types: Set[str],
    max_nodes: int,
) -> Tuple[List[str], List[Tuple[str, str]], bool]:
    """
    Returns (nodes, edges, truncated)
    nodes: list of node_ids
    edges: list of (src, tgt)
    """
    # No focus: render whole (bounded)
    if not focus:
        all_nodes = [
            n.get("id")
            for n in graph.get("nodes", [])
            if isinstance(n, dict) and isinstance(n.get("id"), str)
        ]
        truncated = len(all_nodes) > max_nodes
        nodes = all_nodes[:max_nodes]
        node_set = set(nodes)

        edges: List[Tuple[str, str]] = []
        for s, t in _iter_edges(graph, edge_types):
            if s in node_set and t in node_set:
                edges.append((s, t))
        return sorted(node_set), edges, truncated

    adj = _build_adj(graph, edge_types)
    rev = _build_rev(graph, edge_types)

    q = deque([(focus, 0)])
    seen: Set[str] = set()
    edges_set: Set[Tuple[str, str]] = set()
    truncated = False

    while q:
        cur, d = q.popleft()
        if cur in seen:
            continue

        seen.add(cur)
        if len(seen) > max_nodes:
            truncated = True
            break

        if d >= depth:
            continue

        if direction in ("out", "both"):
            for nb in adj.get(cur, []):
                edges_set.add((cur, nb))
                if nb not in seen:
                    q.append((nb, d + 1))

        if direction in ("in", "both"):
            for nb in rev.get(cur, []):
                edges_set.add((nb, cur))
                if nb not in seen:
                    q.append((nb, d + 1))

    nodes = sorted(seen)
    edges = sorted(edges_set)
    return nodes, edges, truncated


def export_mermaid(
    graph: Dict[str, Any],
    focus: Optional[str] = None,
    direction: str = "out",
    depth: int = 1,
    edge_types: Optional[Set[str]] = None,
    max_nodes: int = 200,
) -> Tuple[str, Dict[str, Any]]:
    edge_types = set(edge_types or DEFAULT_EDGE_TYPES)

    nodes, edges, truncated = _collect_subgraph(
        graph=graph,
        focus=focus,
        direction=direction,
        depth=depth,
        edge_types=edge_types,
        max_nodes=max_nodes,
    )

    idx = {nid: i for i, nid in enumerate(nodes)}
    lines = ["graph TD"]

    for nid in nodes:
        lines.append(f'  n{idx[nid]}["{_label_from_id(nid)}"]')

    edges_rendered = 0
    for s, t in edges:
        if s in idx and t in idx:
            lines.append(f"  n{idx[s]} --> n{idx[t]}")
            edges_rendered += 1

    meta = {
        "focus": focus,
        "edge_types": sorted(edge_types),
        "direction": direction,
        "depth": depth,
        "nodes_rendered": len(nodes),
        "edges_rendered": edges_rendered,
        "truncated": truncated,
    }
    return "\n".join(lines), meta


def export_dot(
    graph: Dict[str, Any],
    focus: Optional[str] = None,
    direction: str = "out",
    depth: int = 1,
    edge_types: Optional[Set[str]] = None,
    max_nodes: int = 200,
) -> Tuple[str, Dict[str, Any]]:
    edge_types = set(edge_types or DEFAULT_EDGE_TYPES)

    nodes, edges, truncated = _collect_subgraph(
        graph=graph,
        focus=focus,
        direction=direction,
        depth=depth,
        edge_types=edge_types,
        max_nodes=max_nodes,
    )

    idx = {nid: i for i, nid in enumerate(nodes)}
    lines = ["digraph G {"]

    for nid in nodes:
        label = _label_from_id(nid).replace('"', '\\"')
        lines.append(f'  n{idx[nid]} [label="{label}"];')

    edges_rendered = 0
    for s, t in edges:
        if s in idx and t in idx:
            lines.append(f"  n{idx[s]} -> n{idx[t]};")
            edges_rendered += 1

    lines.append("}")

    meta = {
        "focus": focus,
        "edge_types": sorted(edge_types),
        "direction": direction,
        "depth": depth,
        "nodes_rendered": len(nodes),
        "edges_rendered": edges_rendered,
        "truncated": truncated,
    }
    return "\n".join(lines), meta
