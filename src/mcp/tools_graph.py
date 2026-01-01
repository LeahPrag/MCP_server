# src/mcp/tools_graph.py
from typing import Optional, Dict, Any
from mcp.server.fastmcp import FastMCP

from src.mcp.graph_inputs import (
    reject_control_chars,
    normalize_resolve_calls,
    normalize_query_type,
)
from src.mcp.graph_service import GraphService


def register_graph_tools(mcp: FastMCP, svc: GraphService) -> None:
    @mcp.tool()
    def build_graph(
        root_path: str,
        granularity: str = "function",
        include_external: bool = False,
        resolve_calls: str = "jedi",
        force_rebuild: bool = False,
        return_graph: bool = False,
    ) -> Dict[str, Any]:
        err = reject_control_chars(root_path)
        if err:
            return {"ok": False, "error": err, "root_path_received": root_path}

        resolve_calls_norm = normalize_resolve_calls(resolve_calls)
        return svc.build_graph(
            root_path=root_path,
            granularity=granularity,
            include_external=include_external,
            resolve_calls=resolve_calls_norm,
            force_rebuild=force_rebuild,
            return_graph=return_graph,
        )

    @mcp.tool()
    def list_cached_graphs() -> Dict[str, Any]:
        return {"ok": True, "graphs": svc.cache.list()}

    @mcp.tool()
    def clear_graph_cache(graph_id: Optional[str] = None) -> Dict[str, Any]:
        return {"ok": True, **svc.cache.clear(graph_id or "all")}

    @mcp.tool()
    def graph_overview(graph_id: str, refresh_if_stale: bool = True) -> Dict[str, Any]:
        return svc.graph_overview(graph_id=graph_id, refresh_if_stale=refresh_if_stale)

    @mcp.tool()
    def search_nodes(graph_id: str, query: str, limit: int = 12, refresh_if_stale: bool = True) -> Dict[str, Any]:
        return svc.search_nodes(graph_id=graph_id, query=query, limit=limit, refresh_if_stale=refresh_if_stale)

    @mcp.tool()
    def query_graph(
        graph_id: str,
        query_type: str,
        target: str,
        path_target: Optional[str] = None,
        refresh_if_stale: bool = True,
    ) -> Dict[str, Any]:
        qt = normalize_query_type(query_type)
        return svc.query_graph(
            graph_id=graph_id,
            query_type=qt,
            target=target,
            path_target=path_target,
            refresh_if_stale=refresh_if_stale,
        )

    @mcp.tool()
    def export_call_graph(
        graph_id: str,
        format: str = "mermaid",
        focus: Optional[str] = None,
        direction: str = "out",
        depth: int = 1,
        refresh_if_stale: bool = True,
    ) -> Dict[str, Any]:
        return svc.export_call_graph(
            graph_id=graph_id,
            format=format,
            focus=focus,
            direction=direction,
            depth=depth,
            refresh_if_stale=refresh_if_stale,
        )

    

    @mcp.tool()
    def call_certainty_gemini(
        graph_id: str,
        target: str,
        model: str = "gemini-2.5-flash",
        api_key: Optional[str] = None,
        temperature: float = 0.2,
        max_output_tokens: int = 10000,
        refresh_if_stale: bool = True,
    ) -> Dict[str, Any]:
        """
        For a target function, send its source code + the graph-extracted callees list to Gemini.
        Gemini returns JSON classifying each callee as always/conditional/unlikely/unknown.
        """
        return svc.call_certainty_gemini(
            graph_id=graph_id,
            target=target,
            model=model,
            api_key=api_key,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            refresh_if_stale=refresh_if_stale,
        )