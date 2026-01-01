# from typing import Optional, Dict, Any, List
# from mcp.server.fastmcp import FastMCP
# from src.analysis.graph_builder import build_project_graph
# from src.analysis.graph_queries import (
#     find_callers,
#     find_callees,
#     find_dependencies,
#     find_reverse_dependencies,
#     find_path,
# )
# from src.analysis.graph_cache import GraphCache
# from src.analysis.graph_viz import export_mermaid, export_dot
# from src.analysis.graph_stats import graph_overview as graph_overview_impl
# from src.analysis.node_resolver import resolve_node_id, suggest_nodes


# mcp = FastMCP("debug_graph_mcp")
# _GRAPH_CACHE = GraphCache(max_entries=8)


# def _build_graph_impl(root: str, granularity: str, include_external: bool, resolve_calls: str) -> Dict[str, Any]:
#     return build_project_graph(
#         root,
#         granularity=granularity,
#         include_external=include_external,
#         resolve_calls=resolve_calls,  
#     )


# def _reject_control_chars(s: str) -> Optional[str]:
#     for ch in s:
#         if ord(ch) < 32:
#             return (
#                 "Path contains control characters (e.g. TAB). "
#                 "In Inspector use forward slashes like C:/Users/.../test_project"
#             )
#     return None


# def _normalize_resolve_calls(v: str) -> str:
#     v = (v or "").strip().lower()
#     if v in {"fast", "no_jedi", "nojedi", "fallback", "fallback_only"}:
#         return "fallback_only"
#     return "jedi"


# def _normalize_query_type(v: str) -> str:
#     v = (v or "").strip().lower()
#     if v in {"outgoing", "callees", "calls", "deps"}:
#         return "callees"
#     if v in {"incoming", "callers", "used_by", "reverse"}:
#         return "callers"
#     if v in {"dependencies", "reachable"}:
#         return "dependencies"
#     if v in {"reverse_dependencies", "reverse-dependencies"}:
#         return "reverse_dependencies"
#     if v in {"path"}:
#         return "path"
#     return v


# # -------------------- Graph tools (graph_id) --------------------

# @mcp.tool()
# def build_graph(
#     root_path: str,
#     granularity: str = "function",
#     include_external: bool = False,
#     resolve_calls: str = "jedi",         
#     force_rebuild: bool = False,
#     return_graph: bool = False,
# ) -> Dict[str, Any]:
#     """
#     resolve_calls:
#       - "jedi" (default): more accurate, uses Jedi to resolve calls
#       - "fallback_only": faster, uses simple heuristics only
#     """
#     err = _reject_control_chars(root_path)
#     if err:
#         return {"ok": False, "error": err, "root_path_received": root_path}

#     resolve_calls = _normalize_resolve_calls(resolve_calls)

#     entry, cached = _GRAPH_CACHE.build_or_get(
#         root_path=root_path,
#         granularity=granularity,
#         include_external=include_external,
#         resolve_calls=resolve_calls,        
#         builder=_build_graph_impl,
#         force_rebuild=force_rebuild,
#     )

#     res = {
#         "ok": True,
#         "graph_id": entry.graph_id,
#         "cached": cached,
#         "root": entry.root,
#         "granularity": entry.granularity,
#         "include_external": entry.include_external,
#         "resolve_calls": entry.resolve_calls,  # ✅ חדש
#         "summary": {
#             "nodes": len(entry.graph.get("nodes", [])),
#             "edges": len(entry.graph.get("edges", [])),
#         },
#     }
#     if return_graph:
#         res["graph"] = entry.graph
#     return res


# @mcp.tool()
# def list_cached_graphs() -> Dict[str, Any]:
#     return {"ok": True, "graphs": _GRAPH_CACHE.list()}


# @mcp.tool()
# def clear_graph_cache(graph_id: Optional[str] = None) -> Dict[str, Any]:
#     return {"ok": True, **_GRAPH_CACHE.clear(graph_id or "all")}


# @mcp.tool()
# def graph_overview(graph_id: str, refresh_if_stale: bool = True) -> Dict[str, Any]:
#     entry = _GRAPH_CACHE.get(graph_id)
#     if not entry:
#         return {"ok": False, "error": "Unknown graph_id. Call build_graph first."}

#     refreshed = False
#     if refresh_if_stale:
#         entry2, refreshed = _GRAPH_CACHE.refresh_if_stale(graph_id, builder=_build_graph_impl)
#         if entry2:
#             entry = entry2

#     return {
#         "ok": True,
#         "graph_id": graph_id,
#         "refreshed": refreshed,
#         "overview": graph_overview_impl(entry.graph),
#     }


# @mcp.tool()
# def search_nodes(graph_id: str, query: str, limit: int = 12, refresh_if_stale: bool = True) -> Dict[str, Any]:
#     entry = _GRAPH_CACHE.get(graph_id)
#     if not entry:
#         return {"ok": False, "error": "Unknown graph_id. Call build_graph first."}

#     refreshed = False
#     if refresh_if_stale:
#         entry2, refreshed = _GRAPH_CACHE.refresh_if_stale(graph_id, builder=_build_graph_impl)
#         if entry2:
#             entry = entry2

#     return {
#         "ok": True,
#         "graph_id": graph_id,
#         "refreshed": refreshed,
#         "matches": suggest_nodes(entry.graph, query, limit=limit),
#         "hint": 'Use returned ids as target/focus (e.g. "func:b.py:process").',
#     }


# @mcp.tool()
# def query_graph(
#     graph_id: str,
#     query_type: str,
#     target: str,
#     path_target: Optional[str] = None,
#     refresh_if_stale: bool = True,
# ) -> Dict[str, Any]:
#     entry = _GRAPH_CACHE.get(graph_id)
#     if not entry:
#         return {"ok": False, "error": "Unknown graph_id. Call build_graph first."}

#     refreshed = False
#     if refresh_if_stale:
#         entry2, refreshed = _GRAPH_CACHE.refresh_if_stale(graph_id, builder=_build_graph_impl)
#         if entry2:
#             entry = entry2

#     g = entry.graph
#     query_type = _normalize_query_type(query_type)

#     resolved_target = resolve_node_id(g, target)
#     if not resolved_target:
#         return {
#             "ok": False,
#             "error": f"Unknown target node id: {target}",
#             "suggestions": suggest_nodes(g, target),
#             "hint": 'Try "func:b.py:process" or call search_nodes(graph_id, "process")',
#         }

#     if query_type in ("callers", "callees"):
#         if query_type == "callers":
#             return {"ok": True, "graph_id": graph_id, "refreshed": refreshed, "result": find_callers(g, resolved_target)}
#         else:
#             return {"ok": True, "graph_id": graph_id, "refreshed": refreshed, "result": find_callees(g, resolved_target)}

#     if query_type == "dependencies":
#         return {"ok": True, "graph_id": graph_id, "refreshed": refreshed, "result": find_dependencies(g, resolved_target)}

#     if query_type == "reverse_dependencies":
#         return {"ok": True, "graph_id": graph_id, "refreshed": refreshed, "result": find_reverse_dependencies(g, resolved_target)}

#     if query_type == "path":
#         if not path_target:
#             return {"ok": False, "error": "query_type=path requires path_target"}
#         resolved_path_target = resolve_node_id(g, path_target)
#         if not resolved_path_target:
#             return {"ok": False, "error": f"Unknown path_target node id: {path_target}", "suggestions": suggest_nodes(g, path_target)}
#         return {"ok": True, "graph_id": graph_id, "refreshed": refreshed, "result": find_path(g, resolved_target, resolved_path_target)}

#     return {
#         "ok": False,
#         "error": f"Unknown query_type: {query_type}",
#         "allowed": ["callers", "callees", "dependencies", "reverse_dependencies", "path"],
#         "aliases": {"outgoing": "callees", "incoming": "callers"},
#     }


# @mcp.tool()
# def export_call_graph(
#     graph_id: str,
#     format: str = "mermaid",
#     focus: Optional[str] = None,
#     direction: str = "out",
#     depth: int = 1,
#     refresh_if_stale: bool = True,
# ) -> Dict[str, Any]:
#     entry = _GRAPH_CACHE.get(graph_id)
#     if not entry:
#         return {"ok": False, "error": "Unknown graph_id. Call build_graph first."}

#     refreshed = False
#     if refresh_if_stale:
#         entry2, refreshed = _GRAPH_CACHE.refresh_if_stale(graph_id, builder=_build_graph_impl)
#         if entry2:
#             entry = entry2

#     g = entry.graph

#     resolved_focus = None
#     if focus:
#         resolved_focus = resolve_node_id(g, focus)
#         if not resolved_focus:
#             return {
#                 "ok": False,
#                 "error": f"Unknown focus node id: {focus}",
#                 "suggestions": suggest_nodes(g, focus),
#                 "hint": 'Try "func:b.py:process" (note func: prefix)',
#             }

#     if format == "dot":
#         dot, meta = export_dot(g, focus=resolved_focus, direction=direction, depth=depth)
#         return {"ok": True, "graph_id": graph_id, "refreshed": refreshed, "dot": dot, "meta": meta}

#     mermaid, meta = export_mermaid(g, focus=resolved_focus, direction=direction, depth=depth)
#     return {"ok": True, "graph_id": graph_id, "refreshed": refreshed, "mermaid": mermaid, "meta": meta}




# if __name__ == "__main__":
#     mcp.run(transport="stdio")

# mcp_server.py
from mcp.server.fastmcp import FastMCP

from src.analysis.graph_cache import GraphCache
from src.mcp.graph_service import GraphService
from src.mcp.tools_graph import register_graph_tools
from pathlib import Path
from dotenv import load_dotenv
# load .env from project root (same folder as mcp_server.py)
load_dotenv(Path(__file__).resolve().parent / ".env")

mcp = FastMCP("debug_graph_mcp")

svc = GraphService(GraphCache(max_entries=8))
register_graph_tools(mcp, svc)


if __name__ == "__main__":
    mcp.run(transport="stdio")
