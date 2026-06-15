#!/usr/bin/env python3
"""adqa-agent MCP server — ADQA knowledge base search."""

import json
import pathlib
import threading
import time
from typing import Optional

from mcp.server.fastmcp import FastMCP
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

REPO_ROOT = pathlib.Path(__file__).parent
KNOWLEDGE_DIR = REPO_ROOT / "knowledge"
THREADS_PATH = KNOWLEDGE_DIR / "threads.jsonl"
TESTS_PATH = KNOWLEDGE_DIR / "tests.jsonl"
PERSONAS_DIR = REPO_ROOT / "personas"
DEFAULT_PERSONA = "aiden_chen"


def _load_persona(name: str) -> str:
    path = PERSONAS_DIR / name / "persona.md"
    if path.exists():
        return path.read_text()
    return ""

_cases: list[dict] = []
_lock = threading.Lock()


def _load() -> list[dict]:
    cases = []
    for path in [THREADS_PATH, TESTS_PATH]:
        if path.exists():
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            cases.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
    return cases


def _reload():
    global _cases
    cases = _load()
    with _lock:
        _cases = cases
    print(f"[adqa-agent] loaded {len(_cases)} cases", flush=True)


class _Reloader(FileSystemEventHandler):
    def on_modified(self, event):
        if not event.is_directory and str(event.src_path).endswith(".jsonl"):
            _reload()

    def on_created(self, event):
        if not event.is_directory and str(event.src_path).endswith(".jsonl"):
            _reload()


_reload()

_observer = Observer()
_observer.schedule(_Reloader(), str(KNOWLEDGE_DIR), recursive=False)
_observer.daemon = True
_observer.start()

mcp = FastMCP(
    "adqa-agent",
    instructions=(
        "ADQA knowledge base: SSP issues, attribution failures, creative bugs, "
        "deeplink problems, CTR anomalies. Use search_knowledge for open questions, "
        "list_cases to browse by SSP or status."
    ),
)


def _score(case: dict, query: str) -> int:
    q = query.lower()
    tokens = q.split()
    fields = [
        case.get("symptom", {}).get("signature", ""),
        case.get("root_cause", {}).get("summary", ""),
        " ".join(case.get("symptom", {}).get("scope_tags", {}).get("ssp", [])),
        " ".join(case.get("symptom", {}).get("funnel_stage", [])),
        case.get("status", ""),
        case.get("notes") or "",
        case.get("resolution", {}).get("fix") or "",
    ]
    combined = " ".join(fields).lower()
    score = 3 if q in combined else 0
    score += sum(1 for t in tokens if t in combined)
    return score


def _fmt(case: dict) -> str:
    sym = case.get("symptom", {})
    rc = case.get("root_cause", {})
    res = case.get("resolution", {})
    prov = case.get("provenance", {})
    related = case.get("related_cases", [])

    related_links = ", ".join(
        f"[{r['key']}](https://appier.atlassian.net/browse/{r['key']})"
        if isinstance(r, dict) else r
        for r in related
    )

    lines = [
        f"**[{case.get('pattern_id', '?')}]**",
        f"症狀：{sym.get('signature', '')}",
        f"根因：{rc.get('summary', '')}",
        f"  confidence={rc.get('confidence', '')} | category={rc.get('category', '')}",
        f"狀態：{case.get('status', '')} | 最後提及：{case.get('last_mentioned', '-')}",
    ]
    if res.get("fix"):
        lines.append(f"修法：{res['fix']}")
    if related_links:
        lines.append(f"相關：{related_links}")
    refs = prov.get("thread_refs", [])
    if refs:
        lines.append(f"來源：{refs[0]}")
    return "\n".join(lines)


@mcp.tool()
def search_knowledge(query: str, persona: Optional[str] = None) -> str:
    """Search the ADQA knowledge base. Ask about SSP issues (Pangle, Mintegral, InMobi, Vungle...), CTR anomalies, deeplink problems, attribution failures, endcard bugs.

    persona: optional tone guide for the response. Available: aiden_chen (default), andy_yu, kochi_chuang, howard_cheng, pineapple_wu.
    When persona is set, apply the persona's tone guidelines when synthesizing your answer from the results below.
    """
    with _lock:
        cases = list(_cases)

    if not cases:
        return "知識庫是空的，請確認 knowledge/threads.jsonl 存在。"

    scored = sorted(
        [(c, _score(c, query)) for c in cases],
        key=lambda x: x[1],
        reverse=True,
    )
    top = [(c, s) for c, s in scored if s > 0][:5]

    if not top:
        result = f"知識庫（{len(cases)} 條）找不到關於「{query}」的案例。"
    else:
        parts = [f"找到 {len(top)} 條相關案例（共 {len(cases)} 條）：\n"]
        for i, (case, _) in enumerate(top, 1):
            parts.append(f"### {i}.\n{_fmt(case)}\n")
        result = "\n".join(parts)

    persona_name = persona or DEFAULT_PERSONA
    persona_text = _load_persona(persona_name)
    if persona_text:
        result += f"\n\n---\n**語氣指南 (persona: {persona_name})**\n{persona_text}"

    return result


@mcp.tool()
def list_cases(ssp: Optional[str] = None, status: Optional[str] = None) -> str:
    """List ADQA cases. Filter by ssp (e.g. 'pangle', 'mintegral', 'inmobi') or status ('resolved', 'known-degradation', 'by-design')."""
    with _lock:
        cases = list(_cases)

    filtered = cases
    if ssp:
        filtered = [
            c for c in filtered
            if ssp.lower() in " ".join(
                c.get("symptom", {}).get("scope_tags", {}).get("ssp", [])
            ).lower()
        ]
    if status:
        filtered = [c for c in filtered if c.get("status") == status]

    if not filtered:
        return f"沒有符合條件的案例（ssp={ssp!r}, status={status!r}）。"

    lines = [f"共 {len(filtered)} 條案例：\n"]
    for c in filtered:
        sym = c.get("symptom", {})
        ssp_tags = ", ".join(sym.get("scope_tags", {}).get("ssp", []))
        lines.append(
            f"- **{c.get('pattern_id')}**\n"
            f"  {sym.get('signature', '')} | {c.get('status')} | "
            f"SSP: {ssp_tags or '-'} | {c.get('last_mentioned', '-')}"
        )
    return "\n".join(lines)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="adqa-agent MCP server")
    parser.add_argument(
        "--transport",
        default="streamable-http",
        choices=["streamable-http", "sse", "stdio"],
    )
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()

    print(f"[adqa-agent] {args.transport} {args.host}:{args.port}", flush=True)

    mcp.settings.host = args.host
    mcp.settings.port = args.port

    try:
        mcp.run(transport=args.transport)
    finally:
        _observer.stop()
        _observer.join()


if __name__ == "__main__":
    main()
