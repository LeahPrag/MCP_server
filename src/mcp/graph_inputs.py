# src/mcp/graph_inputs.py
from typing import Optional

def reject_control_chars(s: str) -> Optional[str]:
    for ch in s:
        if ord(ch) < 32:
            return (
                "Path contains control characters (e.g. TAB). "
                "In Inspector use forward slashes like C:/Users/.../project"
            )
    return None

def normalize_resolve_calls(v: str) -> str:
    v = (v or "").strip().lower()
    if v in {"fast", "no_jedi", "nojedi", "fallback", "fallback_only"}:
        return "fallback_only"
    return "jedi"

def normalize_query_type(v: str) -> str:
    v = (v or "").strip().lower()
    aliases = {
        "outgoing": "callees",
        "calls": "callees",
        "incoming": "callers",
        "used_by": "callers",
        "reachable": "dependencies",
        "rev_deps": "reverse_dependencies",
        "deps": "dependencies",
    }
    return aliases.get(v, v)
