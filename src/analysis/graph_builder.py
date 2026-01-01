import os
import ast
import jedi
from typing import Dict, List, Tuple, Set, Optional

EXCLUDED_DIRS = {
    ".venv", "venv", "env", "__pycache__", ".git", "site-packages",
    "node_modules", "dist", "build",
}

# -------------------- GRAPH STRUCTURE --------------------

class Graph:
    def __init__(self):
        self._nodes = {}   # id -> node dict
        self._edges = set()  # (src, dst, type)

    def add_node(self, id, type, **kw):
        if id not in self._nodes:
            self._nodes[id] = {"id": id, "type": type, **kw}

    def add_edge(self, src, dst, type):
        self._edges.add((src, dst, type))

    def has_node(self, id: str) -> bool:
        return id in self._nodes

    @property
    def nodes(self):
        return list(self._nodes.values())

    @property
    def edges(self):
        return [{"source": s, "target": t, "type": typ} for (s, t, typ) in self._edges]


# -------------------- FILE DISCOVERY --------------------

def find_files(root: str) -> List[str]:
    root = os.path.abspath(root)
    py_files = []

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames
            if d not in EXCLUDED_DIRS and not d.startswith(".")
        ]
        for f in filenames:
            if f.endswith(".py"):
                py_files.append(os.path.join(dirpath, f))

    return py_files


def parse_files(root: str) -> dict:
    root = os.path.abspath(root)
    files = find_files(root)
    data = {}

    for path in files:
        try:
            with open(path, encoding="utf8") as fh:
                src = fh.read()
            tree = ast.parse(src)
        except Exception:
            continue

        rel = os.path.relpath(path, root).replace("\\", "/")
        data[path] = {"rel": rel, "src": src, "tree": tree}

    return data


# -------------------- IMPORT ALIASES --------------------

def extract_aliases(tree) -> Tuple[dict, dict]:
    mod_alias, func_alias = {}, {}
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                mod_alias[a.asname or a.name] = a.name
        elif isinstance(n, ast.ImportFrom) and n.module:
            for a in n.names:
                func_alias[a.asname or a.name] = f"{n.module}.{a.name}"
    return mod_alias, func_alias


# -------------------- FALLBACK RESOLUTION --------------------

def resolve_fallback(func_node, mod_alias, func_alias) -> List[Tuple[str, str]]:
    # case: imported function/class called directly: name(...)
    if isinstance(func_node, ast.Name):
        name = func_node.id
        if name in func_alias:
            full = func_alias[name]  # e.g. utils.c.add
            module, real_name = full.rsplit(".", 1)
            rel_path = module.replace(".", "/") + ".py"
            return [(rel_path, real_name)]
        return []

    # case: module alias call: mod.func(...)
    if isinstance(func_node, ast.Attribute) and isinstance(func_node.value, ast.Name):
        alias = func_node.value.id
        name = func_node.attr

        if alias in mod_alias:
            module = mod_alias[alias]
            rel_path = module.replace(".", "/") + ".py"
            return [(rel_path, name)]

        if alias in func_alias:
            full = func_alias[alias]
            module, real_name = full.rsplit(".", 1)
            rel_path = module.replace(".", "/") + ".py"
            return [(rel_path, real_name)]

    return []


# -------------------- JEDI RESOLUTION (FIXED FOR METHODS) --------------------

def resolve_with_jedi(
    project,
    file_path: str,
    src: str,
    func_node,
    root: str,
    include_external: bool,
) -> List[Tuple[str, str]]:
    """
    Returns list of (target_rel, target_name), where target_name matches our graph node naming:
      - function: "log"
      - method:   "Admin.audit"
    """
    try:
        script = jedi.Script(code=src, path=file_path, project=project)

        line = func_node.lineno
        col = func_node.col_offset

        # IMPORTANT: for Attribute like `admin.audit`, infer at the "audit" token, not at "admin"
        if isinstance(func_node, ast.Attribute) and getattr(func_node, "end_col_offset", None) is not None:
            col = max(func_node.col_offset, func_node.end_col_offset - len(func_node.attr))

        defs = script.infer(line, col)
    except Exception:
        return []

    results = []
    root = os.path.abspath(root)

    for d in defs:
        module_path = d.module_path
        if not module_path:
            if include_external:
                results.append((f"<external>:{d.name}", d.name))
            continue

        module_path = os.path.abspath(str(module_path))
        rel = os.path.relpath(module_path, root).replace("\\", "/")

        # Prefer full_name so we get Class.method when needed
        target_name = d.name
        full_name = getattr(d, "full_name", None)      # e.g. utils.models.Admin.audit
        module_name = getattr(d, "module_name", None)  # e.g. utils.models

        if full_name and module_name and full_name.startswith(module_name + "."):
            # suffix is either "log" or "Admin.audit"
            target_name = full_name[len(module_name) + 1 :]

        results.append((rel, target_name))

    return results


# -------------------- FUNCTION GRAPH --------------------

def build_function_graph(
    root: str,
    include_external: bool = False,
    resolve_calls: str = "jedi",  # "jedi" | "fallback_only"
) -> Graph:
    root = os.path.abspath(root)
    files_data = parse_files(root)
    g = Graph()
    project = jedi.Project(root)

    use_jedi = (resolve_calls == "jedi")

    # collect where each class is defined (for safe resolution)
    class_defs: Dict[str, Set[str]] = {}

    # ---- PASS 1: create nodes (files, classes, functions, methods) ----

    class NodeCollector(ast.NodeVisitor):
        def __init__(self, rel: str):
            self.rel = rel
            self.class_stack: List[str] = []

        def visit_ClassDef(self, node: ast.ClassDef):
            class_name = node.name
            class_defs.setdefault(class_name, set()).add(self.rel)

            file_id = f"file:{self.rel}"
            class_id = f"class:{self.rel}:{class_name}"

            g.add_node(file_id, "file", path=self.rel)
            g.add_node(class_id, "class", file=self.rel, name=class_name)
            g.add_edge(file_id, class_id, "contains")

            self.class_stack.append(class_name)
            self.generic_visit(node)
            self.class_stack.pop()

        def visit_FunctionDef(self, node: ast.FunctionDef):
            file_id = f"file:{self.rel}"
            g.add_node(file_id, "file", path=self.rel)

            if self.class_stack:
                cls = self.class_stack[-1]
                qual = f"{cls}.{node.name}"
                func_id = f"func:{self.rel}:{qual}"
                g.add_node(func_id, "method", file=self.rel, name=node.name, qualname=qual, class_name=cls)

                class_id = f"class:{self.rel}:{cls}"
                g.add_node(class_id, "class", file=self.rel, name=cls)
                g.add_edge(class_id, func_id, "contains")
                g.add_edge(file_id, func_id, "contains")
            else:
                func_id = f"func:{self.rel}:{node.name}"
                g.add_node(func_id, "function", file=self.rel, name=node.name, qualname=node.name)
                g.add_edge(file_id, func_id, "contains")

            self.generic_visit(node)

    for path, info in files_data.items():
        rel = info["rel"]
        NodeCollector(rel).visit(info["tree"])

    def resolve_class_to_rel(class_name: str, current_rel: str, func_alias: dict) -> Optional[Tuple[str, str]]:
        # imported class (from x import Admin)
        if class_name in func_alias:
            full = func_alias[class_name]           # e.g. utils.models.Admin
            module, real_cls = full.rsplit(".", 1)  # utils.models , Admin
            return (module.replace(".", "/") + ".py", real_cls)

        hits = class_defs.get(class_name, set())
        if len(hits) == 1:
            return (next(iter(hits)), class_name)
        if current_rel in hits:
            return (current_rel, class_name)
        return None

    # ---- PASS 2: detect call edges ----

    for path, info in files_data.items():
        rel = info["rel"]
        src = info["src"]
        tree = info["tree"]
        mod_alias, func_alias = extract_aliases(tree)

        class Current(ast.NodeVisitor):
            def __init__(self):
                self.current_class: Optional[str] = None
                self.current_func: Optional[str] = None
                self.local_types: Dict[str, Tuple[str, str]] = {}  # var -> (class_rel, class_name)

            def visit_ClassDef(self, node):
                prev = self.current_class
                self.current_class = node.name
                self.generic_visit(node)
                self.current_class = prev

            def visit_FunctionDef(self, node):
                prev_func = self.current_func
                prev_types = self.local_types

                self.current_func = f"{self.current_class}.{node.name}" if self.current_class else node.name
                self.local_types = {}  # new local scope per function

                self.generic_visit(node)

                self.local_types = prev_types
                self.current_func = prev_func

            def _capture_ctor_assignment(self, target, value):
                if not isinstance(target, ast.Name):
                    return
                if not isinstance(value, ast.Call):
                    return

                ctor = value.func
                cls_name = None
                if isinstance(ctor, ast.Name):
                    cls_name = ctor.id
                elif isinstance(ctor, ast.Attribute):
                    cls_name = ctor.attr

                if not cls_name:
                    return

                resolved = resolve_class_to_rel(cls_name, rel, func_alias)
                if not resolved:
                    return

                self.local_types[target.id] = resolved

            def visit_Assign(self, node):
                for t in node.targets:
                    self._capture_ctor_assignment(t, node.value)
                self.generic_visit(node)

            def visit_AnnAssign(self, node):
                if node.value is not None:
                    self._capture_ctor_assignment(node.target, node.value)
                self.generic_visit(node)

            def visit_Call(self, node):
                if not self.current_func:
                    return

                caller_id = f"func:{rel}:{self.current_func}"
                targets = resolve_fallback(node.func, mod_alias, func_alias)

                if not targets and use_jedi:
                    targets = resolve_with_jedi(project, path, src, node.func, root, include_external)

                # smart fallback for obj.method()
                if not targets and isinstance(node.func, ast.Attribute):
                    method_name = node.func.attr
                    recv = node.func.value

                    # case: var.method() where var type known
                    if isinstance(recv, ast.Name) and recv.id in self.local_types:
                        class_rel, cls = self.local_types[recv.id]
                        targets = [(class_rel, f"{cls}.{method_name}")]

                    # case: Class(...).method()  (chained)
                    elif isinstance(recv, ast.Call):
                        ctor = recv.func
                        cls_name = None
                        if isinstance(ctor, ast.Name):
                            cls_name = ctor.id
                        elif isinstance(ctor, ast.Attribute):
                            cls_name = ctor.attr

                        if cls_name:
                            resolved = resolve_class_to_rel(cls_name, rel, func_alias)
                            if resolved:
                                class_rel, cls = resolved
                                targets = [(class_rel, f"{cls}.{method_name}")]

                # last resort (ONLY if unique) to avoid false positives like 6 instead of 5
                if not targets and isinstance(node.func, ast.Attribute):
                    method_name = node.func.attr
                    cands = [
                        n for n in g.nodes
                        if n.get("type") == "method" and n.get("name") == method_name
                    ]
                    if len(cands) == 1:
                        n = cands[0]
                        targets = [(n["file"], n["qualname"])]

                for target_rel, target_name in targets:
                    callee_id = f"func:{target_rel}:{target_name}"
                    if g.has_node(callee_id):
                        g.add_edge(caller_id, callee_id, "call")

                self.generic_visit(node)

        Current().visit(tree)

    return g


# -------------------- FILE GRAPH --------------------

def build_file_graph(root: str, include_external: bool = False) -> Graph:
    root = os.path.abspath(root)
    files_data = parse_files(root)
    g = Graph()

    module_to_file = {}

    for path, info in files_data.items():
        rel = info["rel"]
        module_name = rel[:-3].replace("/", ".")
        module_to_file[module_name] = rel

        file_id = f"file:{rel}"
        g.add_node(file_id, "file", path=rel)

    for path, info in files_data.items():
        rel = info["rel"]
        tree = info["tree"]
        file_id = f"file:{rel}"

        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                for a in n.names:
                    mod = a.name
                    if mod in module_to_file:
                        target_rel = module_to_file[mod]
                        g.add_edge(file_id, f"file:{target_rel}", "import")

            elif isinstance(n, ast.ImportFrom) and n.module:
                mod = n.module
                if mod in module_to_file:
                    target_rel = module_to_file[mod]
                    g.add_edge(file_id, f"file:{target_rel}", "import")

    return g


# -------------------- PUBLIC API --------------------

def serialize_graph(g: Graph) -> dict:
    return {"nodes": g.nodes, "edges": g.edges}


def build_project_graph(
    root: str,
    granularity: str = "function",
    include_external: bool = False,
    resolve_calls: str = "jedi",  # "jedi" | "fallback_only"
) -> dict:
    if granularity == "file":
        g = build_file_graph(root, include_external)
    else:
        g = build_function_graph(root, include_external, resolve_calls=resolve_calls)
    return serialize_graph(g)

