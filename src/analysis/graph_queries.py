# src/analysis/graph_queries.py

from collections import deque
from typing import List, Dict


def _build_adjacency(graph_data: dict, edge_types: set[str] | None = None) -> dict:
    adj: Dict[str, List[str]] = {}
    for edge in graph_data.get("edges", []):
        if edge_types and edge.get("type") not in edge_types:
            continue
        adj.setdefault(edge["source"], []).append(edge["target"])
    return adj

def _build_reverse_adjacency(graph_data: dict, edge_types: set[str] | None = None) -> dict:
    rev: Dict[str, List[str]] = {}
    for edge in graph_data.get("edges", []):
        if edge_types and edge.get("type") not in edge_types:
            continue
        rev.setdefault(edge["target"], []).append(edge["source"])
    return rev



def find_callers(graph, target_id):
    callers = set()
    for e in graph.get("edges", []):
        if e.get("type") != "call":
            continue
        if e.get("target") == target_id:
            callers.add(e.get("source"))
    return sorted(callers)


def find_callees(graph, source_id):
    callees = set()
    for e in graph.get("edges", []):
        if e.get("type") != "call":
            continue
        if e.get("source") == source_id:
            callees.add(e.get("target"))
    return sorted(callees)


def find_dependencies(graph_data: dict, node_id: str) -> List[str]:
    """
    כל מה שנגיש מ-node_id דרך קשתות קדימה (graph traversal פשוט).
    """
    adj = _build_adjacency(graph_data)
    visited = set()
    stack = [node_id]

    while stack:
        current = stack.pop()
        if current in visited:
            continue
        visited.add(current)
        for neigh in adj.get(current, []):
            if neigh not in visited:
                stack.append(neigh)

    visited.discard(node_id)
    return list(visited)


def find_reverse_dependencies(graph_data: dict, node_id: str) -> List[str]:
    """
    כל מי שיכול להגיע ל-node_id דרך קשתות (תלויות הפוכות).
    """
    rev_adj = _build_reverse_adjacency(graph_data)
    visited = set()
    stack = [node_id]

    while stack:
        current = stack.pop()
        if current in visited:
            continue
        visited.add(current)
        for neigh in rev_adj.get(current, []):
            if neigh not in visited:
                stack.append(neigh)

    visited.discard(node_id)
    return list(visited)


def find_path(graph_data: dict, source_id: str, target_id: str) -> List[str]:
    """
    מסלול כלשהו בין source ל-target (אם קיים), באמצעות BFS.
    """
    adj = _build_adjacency(graph_data)

    queue = deque([source_id])
    parents: Dict[str, str | None] = {source_id: None}

    while queue:
        current = queue.popleft()
        if current == target_id:
            break
        for neigh in adj.get(current, []):
            if neigh not in parents:
                parents[neigh] = current
                queue.append(neigh)

    if target_id not in parents:
        return []

    # reconstruct path
    path = []
    cur = target_id
    while cur is not None:
        path.append(cur)
        cur = parents[cur]
    path.reverse()
    return path
