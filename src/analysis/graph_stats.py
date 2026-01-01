# src/analysis/graph_stats.py
from __future__ import annotations

from typing import Any, Dict
from collections import defaultdict


def graph_overview(graph: Dict[str, Any], edge_type: str = "call", top_n: int = 10) -> Dict[str, Any]:
    nodes = graph.get("nodes", [])
    edges = [e for e in graph.get("edges", []) if e.get("type") == edge_type]

    nodes_by_id = {n.get("id"): n for n in nodes if n.get("id")}

    indeg = defaultdict(int)
    outdeg = defaultdict(int)

    for e in edges:
        s, t = e.get("source"), e.get("target")
        if s and t:
            outdeg[s] += 1
            indeg[t] += 1

    involved = set(indeg.keys()) | set(outdeg.keys())

    def label(nid: str) -> str:
        n = nodes_by_id.get(nid, {})
        if n.get("type") == "file":
            return n.get("path", nid)
        qn = n.get("qualname") or n.get("name") or nid
        file = n.get("file")
        return f"{file}:{qn}" if file else qn

    entrypoints = sorted([nid for nid in involved if indeg.get(nid, 0) == 0 and outdeg.get(nid, 0) > 0])
    leaves = sorted([nid for nid in involved if outdeg.get(nid, 0) == 0 and indeg.get(nid, 0) > 0])

    top_hotspots = sorted(involved, key=lambda nid: indeg.get(nid, 0), reverse=True)[:top_n]
    top_hubs = sorted(involved, key=lambda nid: outdeg.get(nid, 0), reverse=True)[:top_n]

    per_file = defaultdict(lambda: {"functions": 0, "methods": 0, "classes": 0})
    for n in nodes:
        f = n.get("file") or (n.get("path") if n.get("type") == "file" else None)
        if not f:
            continue
        t = n.get("type")
        if t == "function":
            per_file[f]["functions"] += 1
        elif t == "method":
            per_file[f]["methods"] += 1
        elif t == "class":
            per_file[f]["classes"] += 1

    per_file_list = [{"file": k, **v} for k, v in per_file.items()]
    per_file_list.sort(key=lambda x: (x["functions"] + x["methods"] + x["classes"]), reverse=True)

    return {
        "edge_type": edge_type,
        "counts": {
            "nodes_total": len(nodes),
            "edges_total": len(graph.get("edges", [])),
            "edges_of_type": len(edges),
            "nodes_involved_in_edges": len(involved),
        },
        "entrypoints": [label(n) for n in entrypoints[:top_n]],
        "leaves": [label(n) for n in leaves[:top_n]],
        "top_hotspots_by_fanin": [{"node": label(n), "fanin": indeg.get(n, 0)} for n in top_hotspots],
        "top_hubs_by_fanout": [{"node": label(n), "fanout": outdeg.get(n, 0)} for n in top_hubs],
        "per_file": per_file_list[:top_n],
        "note": "Entrypoints/leaves relevant mainly for -call graph.",
    }
