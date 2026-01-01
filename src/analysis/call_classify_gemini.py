
from __future__ import annotations

import ast
import json
import os
from typing import Any, Dict, List, Optional

import requests


# -------------------- tiny .env loader (no dependency) --------------------

def _load_dotenv_if_exists(env_path: Optional[str] = None) -> None:
    """
    Minimal .env loader: reads KEY=VALUE lines into os.environ if not already set.
    """
    env_path = env_path or ".env"
    if not os.path.exists(env_path):
        return
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v
    except Exception:
        # If dotenv fails, we just rely on normal env vars.
        return


# -------------------- code extraction --------------------

def _read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _find_function_node(tree: ast.AST, qualname: str) -> Optional[ast.AST]:
    """
    qualname examples:
      - "query_graph"
      - "GraphService.query_graph"
      - "Outer.Inner.method"
    """
    parts = qualname.split(".")
    if len(parts) == 1:
        fn_name = parts[0]
        for n in tree.body:  # type: ignore[attr-defined]
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == fn_name:
                return n
        return None

    # Walk classes by name
    cls_parts, fn_name = parts[:-1], parts[-1]
    current_body = getattr(tree, "body", [])
    cls_node = None

    for cls_name in cls_parts:
        cls_node = None
        for n in current_body:
            if isinstance(n, ast.ClassDef) and n.name == cls_name:
                cls_node = n
                break
        if not cls_node:
            return None
        current_body = cls_node.body

    # Find method in that class
    for n in current_body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == fn_name:
            return n
    return None


def extract_qualname_source(
    file_abs: str,
    qualname: str,
    max_lines: int = 240,
) -> Dict[str, Any]:
    """
    Returns: { code, start_line, end_line, truncated }
    """
    src = _read_text(file_abs)
    tree = ast.parse(src)

    node = _find_function_node(tree, qualname)
    if not node or not hasattr(node, "lineno"):
        # Fallback: return top of file (still useful)
        lines = src.splitlines()
        snippet = "\n".join(lines[:max_lines])
        return {"code": snippet, "start_line": 1, "end_line": min(len(lines), max_lines), "truncated": len(lines) > max_lines}

    start = int(getattr(node, "lineno", 1))
    end = int(getattr(node, "end_lineno", start))

    lines = src.splitlines()
    # Python lineno is 1-based
    block = lines[start - 1 : end]
    truncated = False

    if len(block) > max_lines:
        block = block[:max_lines]
        truncated = True
        end = start + max_lines - 1

    return {"code": "\n".join(block), "start_line": start, "end_line": end, "truncated": truncated}


# -------------------- Gemini call (JSON-only) --------------------

def _gemini_generate_json(
    prompt: str,
    api_key: str,
    model: str,
    temperature: float,
    max_output_tokens: int,
) -> Dict[str, Any]:
    """
    Uses Gemini generateContent with responseMimeType=application/json.
    Returns parsed JSON dict or raises ValueError.
    """
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    params = {"key": api_key}

    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_output_tokens,
            "responseMimeType": "application/json",
        },
    }

    r = requests.post(url, params=params, json=payload, timeout=60)
    r.raise_for_status()
    data = r.json()

    # Typical shape: candidates[0].content.parts[0].text
    text = ""
    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception:
        # Some responses return inline JSON differently; fallback to string dump
        text = json.dumps(data)

    text = (text or "").strip()

    # Strict parse first
    try:
        return json.loads(text)
    except Exception:
        # Best-effort extraction: first "{" ... last "}"
        a = text.find("{")
        b = text.rfind("}")
        if a != -1 and b != -1 and b > a:
            chunk = text[a : b + 1]
            return json.loads(chunk)
        raise ValueError(f"Gemini did not return valid JSON. Raw: {text[:300]}...")


def build_call_certainty_prompt(
    *,
    target_id: str,
    code: str,
    callees: List[str],
    truncated: bool,
) -> str:
    callees_lines = "\n".join(f"- {c}" for c in callees)

    return f"""
You are analyzing a single Python function.

GOAL:
For each callee in the provided list, classify whether the call is:
- "always": guaranteed to execute on every normal execution of this function (no early return/raise before it).
- "conditional": only executes on some paths (if/else, loops, try/except, short-circuit, guards, etc.).
- "unlikely": appears in code that is effectively unreachable (after return/raise, dead branch), based on the function body.
- "unknown": cannot decide from this function body alone.

IMPORTANT:
- Use ONLY the function body below. Do not assume runtime inputs.
- Return ONLY valid JSON (no markdown, no backticks, no extra text).
- Output must match this schema exactly:
{{
  "target_id": "string",
  "truncated": true/false,
  "summary": "1-2 sentences",
  "calls": [
    {{
      "callee_id": "string",
      "certainty": "always|conditional|unlikely|unknown",
      "why": "one short sentence"
    }}
  ]
}}
- Double check your output for missing commas, brackets, or quotes. The output must be valid JSON and parsable by Python's json.loads().
- Do NOT add any explanation, markdown, or text before/after the JSON.
- If you cannot classify a callee, use "unknown" and explain why.

TARGET_ID:
{target_id}

CALLEES (from static graph):
{callees_lines}

FUNCTION SOURCE (may be truncated={str(truncated).lower()}):
{code}
""".strip()


def classify_callees_with_gemini(
    *,
    root_abs: str,
    target_node: Dict[str, Any],
    target_id: str,
    callees: List[str],
    api_key: Optional[str],
    model: str,
    temperature: float,
    max_output_tokens: int,
) -> Dict[str, Any]:
    _load_dotenv_if_exists(os.path.join(root_abs, ".env"))
    api_key = api_key or os.getenv("GEMINI_API_KEY")
    if not api_key:
        return {"ok": False, "error": "Missing GEMINI_API_KEY env var or api_key param"}

    file_rel = (target_node.get("file") or "").replace("\\", "/")
    qualname = target_node.get("qualname") or target_node.get("name") or ""
    if not file_rel or not qualname:
        return {"ok": False, "error": "Target node missing 'file' or 'qualname' fields"}

    file_abs = os.path.join(root_abs, file_rel.replace("/", os.sep))
    if not os.path.exists(file_abs):
        return {"ok": False, "error": f"Target file not found: {file_abs}"}

    code_meta = extract_qualname_source(file_abs=file_abs, qualname=qualname, max_lines=240)
    prompt = build_call_certainty_prompt(
        target_id=target_id,
        code=code_meta["code"],
        callees=callees,
        truncated=bool(code_meta["truncated"]),
    )

    try:
        parsed = _gemini_generate_json(
            prompt=prompt,
            api_key=api_key,
            model=model,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        )
    except Exception as e:
        return {
            "ok": False,
            "error": f"Gemini call/parse failed: {e}",
            "code_meta": {
                "file_rel": file_rel,
                "file_abs": file_abs,
                "qualname": qualname,
                "start_line": code_meta["start_line"],
                "end_line": code_meta["end_line"],
                "truncated": code_meta["truncated"],
            },
        }

    # Minimal validation (so you don't get weird partial objects)
    if not isinstance(parsed, dict) or "calls" not in parsed or not isinstance(parsed.get("calls"), list):
        return {"ok": False, "error": "Gemini returned JSON but not in expected schema", "raw_json": parsed}

    return {
        "ok": True,
        "target_id": target_id,
        "code_meta": {
            "file_rel": file_rel,
            "file_abs": file_abs,
            "qualname": qualname,
            "start_line": code_meta["start_line"],
            "end_line": code_meta["end_line"],
            "truncated": code_meta["truncated"],
        },
        "gemini_json": parsed,
    }
