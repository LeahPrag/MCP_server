# src/mcp/graph_service.py
from ast import List
from typing import Any, Dict, Optional, Tuple

from src.analysis.graph_builder import build_project_graph
from src.analysis.graph_cache import GraphCache
from src.analysis.graph_stats import graph_overview as graph_overview_impl
from src.analysis.graph_queries import (
    find_callers, find_callees, find_dependencies, find_reverse_dependencies, find_path
)
from src.analysis.graph_viz import export_mermaid, export_dot
from src.analysis.node_resolver import resolve_node_id, suggest_nodes
from src.analysis.call_classify_gemini import classify_callees_with_gemini

class GraphService:
    def __init__(self, cache: GraphCache):
        self.cache = cache

    def _build_graph_impl(
        self,
        root_path: str,
        granularity: str,
        include_external: bool,
        resolve_calls: str,
    ) -> Dict[str, Any]:
        return build_project_graph(
            root_path,
            granularity=granularity,
            include_external=include_external,
            resolve_calls=resolve_calls,
        )

    def build_graph(
        self,
        root_path: str,
        granularity: str = "function",
        include_external: bool = False,
        resolve_calls: str = "jedi",
        force_rebuild: bool = False,
        return_graph: bool = False,
    ) -> Dict[str, Any]:
        entry, cached = self.cache.build_or_get(
            root_path=root_path,
            granularity=granularity,
            include_external=include_external,
            resolve_calls=resolve_calls,
            builder=self._build_graph_impl,
            force_rebuild=force_rebuild,
        )

        res: Dict[str, Any] = {
            "ok": True,
            "graph_id": entry.graph_id,
            "cached": cached,
            "root": entry.root,
            "granularity": entry.granularity,
            "include_external": entry.include_external,
            "resolve_calls": getattr(entry, "resolve_calls", resolve_calls),
            "summary": {
                "nodes": len(entry.graph.get("nodes", [])),
                "edges": len(entry.graph.get("edges", [])),
            },
        }
        if return_graph:
            res["graph"] = entry.graph
        return res

    def _get_entry(self, graph_id: str, refresh_if_stale: bool) -> Tuple[Optional[Any], bool, Optional[Dict[str, Any]]]:
        entry = self.cache.get(graph_id)
        if not entry:
            return None, False, {"ok": False, "error": "Unknown graph_id. Call build_graph first."}

        refreshed = False
        if refresh_if_stale:
            entry2, refreshed = self.cache.refresh_if_stale(graph_id, builder=self._build_graph_impl)
            if entry2:
                entry = entry2

        return entry, refreshed, None

    def graph_overview(self, graph_id: str, refresh_if_stale: bool = True) -> Dict[str, Any]:
        entry, refreshed, err = self._get_entry(graph_id, refresh_if_stale)
        if err:
            return err
        return {"ok": True, "graph_id": graph_id, "refreshed": refreshed, "overview": graph_overview_impl(entry.graph)}

    def search_nodes(self, graph_id: str, query: str, limit: int = 12, refresh_if_stale: bool = True) -> Dict[str, Any]:
        entry, refreshed, err = self._get_entry(graph_id, refresh_if_stale)
        if err:
            return err
        return {
            "ok": True,
            "graph_id": graph_id,
            "refreshed": refreshed,
            "matches": suggest_nodes(entry.graph, query, limit=limit),
            "hint": 'Use returned ids as target/focus (e.g. "func:b.py:process").',
        }

    def query_graph(
        self,
        graph_id: str,
        query_type: str,
        target: str,
        path_target: Optional[str] = None,
        refresh_if_stale: bool = True,
    ) -> Dict[str, Any]:
        entry, refreshed, err = self._get_entry(graph_id, refresh_if_stale)
        if err:
            return err

        g = entry.graph
        resolved_target = resolve_node_id(g, target)
        if not resolved_target:
            return {
                "ok": False,
                "error": f"Unknown target node id: {target}",
                "suggestions": suggest_nodes(g, target),
                "hint": 'Try "func:b.py:process" or call search_nodes(graph_id, "process")',
            }

        if query_type == "callers":
            return {"ok": True, "graph_id": graph_id, "refreshed": refreshed, "result": find_callers(g, resolved_target)}
        if query_type == "callees":
            return {"ok": True, "graph_id": graph_id, "refreshed": refreshed, "result": find_callees(g, resolved_target)}
        if query_type == "dependencies":
            return {"ok": True, "graph_id": graph_id, "refreshed": refreshed, "result": find_dependencies(g, resolved_target)}
        if query_type == "reverse_dependencies":
            return {"ok": True, "graph_id": graph_id, "refreshed": refreshed, "result": find_reverse_dependencies(g, resolved_target)}
        if query_type == "path":
            if not path_target:
                return {"ok": False, "error": "query_type=path requires path_target"}
            resolved_path_target = resolve_node_id(g, path_target)
            if not resolved_path_target:
                return {"ok": False, "error": f"Unknown path_target node id: {path_target}", "suggestions": suggest_nodes(g, path_target)}
            return {"ok": True, "graph_id": graph_id, "refreshed": refreshed, "result": find_path(g, resolved_target, resolved_path_target)}

        return {
            "ok": False,
            "error": f"Unknown query_type: {query_type}",
            "allowed": ["callers", "callees", "dependencies", "reverse_dependencies", "path"],
            "aliases": {"outgoing": "callees", "incoming": "callers"},
        }

    def export_call_graph(
        self,
        graph_id: str,
        format: str = "mermaid",
        focus: Optional[str] = None,
        direction: str = "out",
        depth: int = 1,
        refresh_if_stale: bool = True,
    ) -> Dict[str, Any]:
        entry, refreshed, err = self._get_entry(graph_id, refresh_if_stale)
        if err:
            return err

        g = entry.graph
        resolved_focus = None
        if focus:
            resolved_focus = resolve_node_id(g, focus)
            if not resolved_focus:
                return {
                    "ok": False,
                    "error": f"Unknown focus node id: {focus}",
                    "suggestions": suggest_nodes(g, focus),
                    "hint": 'Try "func:b.py:process" (note func: prefix)',
                }

        if format == "dot":
            dot, meta = export_dot(g, focus=resolved_focus, direction=direction, depth=depth)
            return {"ok": True, "graph_id": graph_id, "refreshed": refreshed, "dot": dot, "meta": meta}

        mermaid, meta = export_mermaid(g, focus=resolved_focus, direction=direction, depth=depth)
        return {"ok": True, "graph_id": graph_id, "refreshed": refreshed, "mermaid": mermaid, "meta": meta}

    

    def call_certainty_gemini(
        self,
        graph_id: str,
        target: str,
        model: str = "gemini-2.5-flash",
        api_key: Optional[str] = None,
        temperature: float = 0.2,
        max_output_tokens: int = 10000,
        refresh_if_stale: bool = True,
    ) -> Dict[str, Any]:
        entry, refreshed, err = self._get_entry(graph_id, refresh_if_stale)
        if err:
            return err

        g = entry.graph
        resolved_target = resolve_node_id(g, target)
        if not resolved_target:
            return {
                "ok": False,
                "error": f"Unknown target node id: {target}",
                "suggestions": suggest_nodes(g, target),
                "hint": 'Try search_nodes(graph_id, "query_graph") and use returned id',
            }

        # find node dict
        target_node = None
        for n in g.get("nodes", []):
            if isinstance(n, dict) and n.get("id") == resolved_target:
                target_node = n
                break
        if not target_node:
            return {"ok": False, "error": f"Target node not found in graph: {resolved_target}"}

        # callees from graph edges (direct calls)
        callees = find_callees(g, resolved_target)

        
        if max_output_tokens > 4096:
            max_output_tokens = 4096

        ai = classify_callees_with_gemini(
            root_abs=entry.root,
            target_node=target_node,
            target_id=resolved_target,
            callees=callees,
            api_key=api_key,
            model=model,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        )


        return {
            "ok": ai.get("ok", False),
            "graph_id": graph_id,
            "refreshed": refreshed,
            "target_resolved": resolved_target,
            "callees": callees,
            "gemini": ai,
        }