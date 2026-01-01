# src/analysis/graph_cache.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple, List
import os
import uuid


_EXCLUDE_DIRS = {".git", "__pycache__", ".venv", "venv", "env", "node_modules", "dist", "build"}


@dataclass
class GraphEntry:
    graph_id: str
    root: str
    granularity: str
    include_external: bool
    resolve_calls: str
    signature: Tuple[Tuple[str, int, int], ...]  # (relpath, mtime, size)
    graph: Dict[str, Any]


class GraphCache:
    def __init__(self, max_entries: int = 8):
        self.max_entries = max_entries
        self._by_id: Dict[str, GraphEntry] = {}
        self._by_key: Dict[Tuple[str, str, bool, str], str] = {}  # (root, granularity, include_external, resolve_calls) -> graph_id
        self._lru: List[str] = []

    def _compute_signature(self, root_path: str) -> Tuple[Tuple[str, int, int], ...]:
        root = os.path.abspath(root_path)
        items: List[Tuple[str, int, int]] = []

        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in _EXCLUDE_DIRS]
            for f in filenames:
                if not f.endswith(".py"):
                    continue
                full = os.path.join(dirpath, f)
                try:
                    st = os.stat(full)
                except OSError:
                    continue
                rel = os.path.relpath(full, root).replace("\\", "/")
                items.append((rel, int(st.st_mtime), int(st.st_size)))

        items.sort()
        return tuple(items)

    def _touch_lru(self, graph_id: str) -> None:
        if graph_id in self._lru:
            self._lru.remove(graph_id)
        self._lru.insert(0, graph_id)

        while len(self._lru) > self.max_entries:
            evict = self._lru.pop()
            self._evict(evict)

    def _evict(self, graph_id: str) -> None:
        entry = self._by_id.pop(graph_id, None)
        if not entry:
            return
        key = (entry.root, entry.granularity, entry.include_external, entry.resolve_calls)
        self._by_key.pop(key, None)

    def get(self, graph_id: str) -> Optional[GraphEntry]:
        entry = self._by_id.get(graph_id)
        if entry:
            self._touch_lru(graph_id)
        return entry

    def list(self) -> List[Dict[str, Any]]:
        out = []
        for gid in self._lru:
            e = self._by_id.get(gid)
            if not e:
                continue
            out.append(
                {
                    "graph_id": e.graph_id,
                    "root": e.root,
                    "granularity": e.granularity,
                    "include_external": e.include_external,
                    "resolve_calls": e.resolve_calls,
                    "nodes": len(e.graph.get("nodes", [])),
                    "edges": len(e.graph.get("edges", [])),
                }
            )
        return out

    def clear(self, which: str = "all") -> Dict[str, Any]:
        if which == "all":
            n = len(self._by_id)
            self._by_id.clear()
            self._by_key.clear()
            self._lru.clear()
            return {"cleared": "all", "count": n}

        entry = self._by_id.get(which)
        if not entry:
            return {"cleared": which, "count": 0}

        self._evict(which)
        if which in self._lru:
            self._lru.remove(which)
        return {"cleared": which, "count": 1}

 
    def build_or_get(
        self,
        root_path: str,
        granularity: str,
        include_external: bool,
        resolve_calls: str,
        builder: Callable[[str, str, bool, str], Dict[str, Any]],
        force_rebuild: bool = False,
    ) -> Tuple[GraphEntry, bool]:
        root = os.path.abspath(root_path)
        resolve_calls = (resolve_calls or "jedi").strip().lower()
        key = (root, granularity, include_external, resolve_calls)

        if not force_rebuild and key in self._by_key:
            gid = self._by_key[key]
            entry = self._by_id.get(gid)
            if entry:
                self._touch_lru(gid)
                return entry, True

        signature = self._compute_signature(root)
        graph = builder(root, granularity, include_external, resolve_calls)

        gid = str(uuid.uuid4())
        entry = GraphEntry(
            graph_id=gid,
            root=root,
            granularity=granularity,
            include_external=include_external,
            resolve_calls=resolve_calls,
            signature=signature,
            graph=graph,
        )

        self._by_id[gid] = entry
        self._by_key[key] = gid
        self._touch_lru(gid)
        return entry, False


    def refresh_if_stale(
        self,
        graph_id: str,
        builder: Callable[[str, str, bool, str], Dict[str, Any]],
    ) -> Tuple[Optional[GraphEntry], bool]:
        entry = self._by_id.get(graph_id)
        if not entry:
            return None, False

        new_sig = self._compute_signature(entry.root)
        if new_sig == entry.signature:
            self._touch_lru(graph_id)
            return entry, False

        graph = builder(entry.root, entry.granularity, entry.include_external, entry.resolve_calls)
        entry.signature = new_sig
        entry.graph = graph
        self._touch_lru(graph_id)
        return entry, True
