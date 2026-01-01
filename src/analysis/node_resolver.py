# src/analysis/node_resolver.py
from typing import Any, Dict, List, Optional

_QUERY_SYNONYMS = {
    "outgoing": "callees",
    "incoming": "callers",
    "deps": "dependencies",
    "rev_deps": "reverse_dependencies",
}

def coerce_query_type(qt: str) -> str:
    return _QUERY_SYNONYMS.get(qt, qt)

def resolve_node_id(graph: Dict[str, Any], ref: Optional[str]) -> Optional[str]:
    """
    Accepts:
      - full ids: func:..., file:..., class:...
      - short refs: b.py:process  -> func:b.py:process
      - file path: b.py          -> file:b.py
      - suffix match: "process"  -> first node whose id endswith ":process"
    """
    if not ref:
        return None

    nodes = [n for n in graph.get("nodes", []) if isinstance(n, dict) and n.get("id")]
    ids = set(n["id"] for n in nodes)

    if ref in ids:
        return ref

    # Already prefixed but not found
    if ref.startswith(("func:", "file:", "class:")):
        return None

    # file short
    if ref.endswith(".py") and ".py:" not in ref:
        cand = "file:" + ref
        return cand if cand in ids else None

    # function/class short: b.py:process
    if ".py:" in ref:
        cand = "func:" + ref
        if cand in ids:
            return cand
        cand2 = "class:" + ref
        if cand2 in ids:
            return cand2

    # suffix match (best effort)
    for nid in ids:
        if nid.endswith(ref):
            return nid

    return None

def suggest_nodes(graph: Dict[str, Any], needle: str, limit: int = 12) -> List[str]:
    out = []
    for n in graph.get("nodes", []):
        nid = (n or {}).get("id", "")
        if needle in nid:
            out.append(nid)
            if len(out) >= limit:
                break
    return out
