# mcp_server.py
from mcp.server.fastmcp import FastMCP

from src.analysis.graph_cache import GraphCache
from src.mcp.graph_service import GraphService
from src.mcp.tools_graph import register_graph_tools
from pathlib import Path
from dotenv import load_dotenv
# load .env from project root (same folder as server.py)
load_dotenv(Path(__file__).resolve().parent / ".env")

mcp = FastMCP("debug_graph_mcp")


svc = GraphService(GraphCache(max_entries=8))
register_graph_tools(mcp, svc)


if __name__ == "__main__":
    mcp.run(transport="stdio")
