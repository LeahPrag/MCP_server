#  mcp_server.py
import sys
import subprocess
from typing import Optional, Dict, Any

from mcp.server.fastmcp import FastMCP
from src.analysis.ast_analysis import analyze_code
from src.analysis.graph_builder import build_project_graph, serialize_graph
from src.analysis.graph_queries import (
    find_callers,
    find_callees,
    find_dependencies,
    find_reverse_dependencies,
    find_path,
)
from stackoverflow_mcp.so_resolver import so_resolve

import re
from typing import Optional

def _sanitize_traceback(tb: str, max_chars: int = 2500) -> str:
    tb = (tb or "")[-max_chars:]
    # להוריד נתיבי קבצים כדי לא להדליף מידע
    tb = re.sub(r"[A-Za-z]:\\\\[^\\s]+", "<path>", tb)  # Windows
    tb = re.sub(r"/[^\\s]+", "<path>", tb)              # Linux/Mac
    return tb

def _extract_error_query(tb: str) -> str:
    tb = _sanitize_traceback(tb)
    lines = [ln.strip() for ln in tb.splitlines() if ln.strip()]
    if not lines:
        return "python error"

    # חיפוש השורה האחרונה שנראית כמו Exception/Error
    for ln in reversed(lines):
        if re.search(r"(Error|Exception)\s*:", ln):
            return f"python {ln}"

    return f"python {lines[-1]}"
# -----------------------------
# MCP INIT
# -----------------------------

mcp = FastMCP("debug_graph_mcp")

# Cache for project graphs
_PROJECT_GRAPH_CACHE: Dict[str, Any] = {}


# -----------------------------
# run_code — subprocess clean
# -----------------------------

@mcp.tool()
def run_code(code: str, timeout_seconds: int = 5, input_data: Optional[str] = None):
    """
    Execute Python code in a clean subprocess.
    Works reliably with Claude Desktop + FastMCP.
    """
    try:
        p = subprocess.run(
            [sys.executable, "-u", "-c", code],
            input=(input_data or ""),
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            shell=False,
        )
        return {
            "ok": True,
            "returncode": p.returncode,
            "stdout": p.stdout,
            "stderr": p.stderr,
        }
    except subprocess.TimeoutExpired as e:
        return {
            "ok": False,
            "error": "timeout",
            "stdout": (e.stdout or ""),
            "stderr": (e.stderr or ""),
        }
# -----------------------------
# run_code_with_so — subprocess clean
# -----------------------------


@mcp.tool()
async def run_code_with_so(
    code: str,
    timeout_seconds: int = 5,
    input_data: Optional[str] = None,
    tagged: Optional[list[str]] = None,
    top_n: int = 5,
):
    """
    מריץ קוד; אם נפל - מחפש ב-StackOverflow ומחזיר כיוון לפתרון.
    """
    run = run_code(code=code, timeout_seconds=timeout_seconds, input_data=input_data)

    # הצלחה
    if run.get("ok") and int(run.get("returncode") or 0) == 0:
        return {"ok": True, "run": run}

    tb = run.get("stderr") or run.get("stdout") or ""
    query = _extract_error_query(tb)

    so = await so_resolve(
        query=query,
        tagged=(tagged or ["python"]),
        top_n=top_n,
        prefer_accepted=True,
    )

    return {
        "ok": False,
        "run": run,
        "so_query": query,
        "so": so,
    }
from typing import Optional
from src.analysis.so_resolver import so_resolve as so_resolve_impl

@mcp.tool()
async def so_resolve(
    query: str,
    tagged: Optional[list[str]] = None,
    top_n: int = 5,
    prefer_accepted: bool = True,
):
    return await so_resolve_impl(
        query=query,
        tagged=tagged,
        top_n=top_n,
        prefer_accepted=prefer_accepted,
    )

# -----------------------------
# analyze_snippet — AST analysis
# -----------------------------


@mcp.tool()
def analyze_snippet(code: str):
    """
    Analyze Python code using AST.
    """
    try:
        result = analyze_code(code)
        return {"ok": True, "analysis": result}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# -----------------------------
# build_project_graph
# -----------------------------


@mcp.tool()
def build_project_graph_tool(root_path: str, granularity: str = "file"):
    """
    Build a project graph and store it in memory.
    """
    try:
        # graph = build_project_graph(root_path, granularity=granularity)
        # graph_data = serialize_graph(graph)
        graph_data = build_project_graph(root_path, granularity=granularity)

        _PROJECT_GRAPH_CACHE[root_path] = graph_data
        
        return {"ok": True, "graph": graph_data}
    except Exception as e:
        return {"ok": False, "error": str(e)}



# -----------------------------
# query_project_graph
# -----------------------------


@mcp.tool()
def query_project_graph(
    root_path: str,
    query_type: str,
    target: str,
    granularity: str = "file",
    path_target: Optional[str] = None,
):
    """
    Query the project graph.
    """
    try:
        graph_data = _PROJECT_GRAPH_CACHE.get(root_path)

        if not graph_data:
            # graph = build_project_graph(root_path, granularity=granularity)
            # graph_data = serialize_graph(graph)
            graph_data = build_project_graph(root_path, granularity=granularity)

            _PROJECT_GRAPH_CACHE[root_path] = graph_data

        if query_type == "callers":
            results = find_callers(graph_data, target)
        elif query_type == "callees":
            results = find_callees(graph_data, target)
        elif query_type == "dependencies":
            results = find_dependencies(graph_data, target)
        elif query_type == "reverse_dependencies":
            results = find_reverse_dependencies(graph_data, target)
        elif query_type == "path":
            results = find_path(graph_data, target, path_target)
        else:
            return {"ok": False, "error": f"Unknown query_type: {query_type}"}

        return {
            "ok": True,
            "query_type": query_type,
            "target": target,
            "results": results,
        }

    except Exception as e:
        return {"ok": False, "error": str(e)}


# -----------------------------
# echo (debug)
# -----------------------------

@mcp.tool()
def echo(text: str):
    return {"echo": text}


# -----------------------------
# MAIN
# -----------------------------

if __name__ == "__main__":
    mcp.run(transport="stdio")



# # command: C:/Users/user1/Documents/leah/Bootkamp/MCP_server/.venv/Scripts/python.exe
# # arguments: C:/Users/user1/Documents/leah/Bootkamp/MCP_server/mcp_server.py

