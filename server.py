#!/usr/bin/env python3
"""adqa-agent MCP server — ADQA knowledge base search."""

import getpass
import json
import os
import pathlib
import re
import subprocess
import threading
import time
from datetime import datetime, timezone
from typing import Optional

import anthropic

from mcp.server.fastmcp import FastMCP
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

REPO_ROOT = pathlib.Path(__file__).parent
KNOWLEDGE_DIR = REPO_ROOT / "knowledge"
THREADS_PATH = KNOWLEDGE_DIR / "threads.jsonl"
TESTS_PATH = KNOWLEDGE_DIR / "tests.jsonl"
FRONTLINE_PATH = KNOWLEDGE_DIR / "frontline.jsonl"
FRONTLINE_INDEX_PATH = KNOWLEDGE_DIR / "frontline_index.json"
PERSONAS_DIR = REPO_ROOT / "personas"
DEFAULT_PERSONA = "aiden_chen"


def _load_persona(name: str) -> str:
    path = PERSONAS_DIR / name / "persona.md"
    if path.exists():
        return path.read_text()
    return ""


def _get_anthropic_client() -> anthropic.Anthropic:
    # Try Claude Code's macOS keychain entry first
    try:
        user = getpass.getuser()
        r = subprocess.run(
            ["security", "find-generic-password", "-s", "Claude Code-credentials", "-a", user, "-w"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0:
            data = json.loads(r.stdout.strip())
            token = data.get("claudeAiOauth", {}).get("accessToken", "")
            if token:
                return anthropic.Anthropic(auth_token=token)
    except Exception:
        pass
    # Fallback to env var
    return anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))


def _apply_persona(persona_text: str, query: str, raw_results: str) -> str:
    try:
        client = _get_anthropic_client()
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            system=persona_text,
            messages=[{
                "role": "user",
                "content": (
                    f"以下是知識庫搜尋結果，關於問題：「{query}」\n\n"
                    f"{raw_results}\n\n"
                    f"請用你的語氣和風格回答這個問題。"
                ),
            }],
        )
        return msg.content[0].text
    except Exception as e:
        return f"{raw_results}\n\n[persona synthesis failed: {e}]"

_cases: list[dict] = []
_lock = threading.Lock()

_frontline: list[dict] = []
_frontline_lock = threading.Lock()


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


def _load_frontline() -> list[dict]:
    items = []
    if FRONTLINE_PATH.exists():
        with open(FRONTLINE_PATH) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        items.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    return items


def _reload():
    global _cases
    cases = _load()
    with _lock:
        _cases = cases
    print(f"[adqa-agent] loaded {len(_cases)} cases", flush=True)


def _reload_frontline():
    global _frontline
    items = _load_frontline()
    with _frontline_lock:
        _frontline = items
    print(f"[adqa-agent] loaded {len(_frontline)} frontline items", flush=True)


class _Reloader(FileSystemEventHandler):
    def on_modified(self, event):
        if not event.is_directory and str(event.src_path).endswith(".jsonl"):
            path = str(event.src_path)
            if "frontline" in path:
                _reload_frontline()
            else:
                _reload()

    def on_created(self, event):
        if not event.is_directory and str(event.src_path).endswith(".jsonl"):
            path = str(event.src_path)
            if "frontline" in path:
                _reload_frontline()
            else:
                _reload()


_reload()
_reload_frontline()

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


def _tokenize(query: str) -> list[str]:
    q = query.lower()
    tokens = set(q.split())
    tokens.update(re.findall(r'[a-z0-9]+', q))
    for seq in re.findall(r'[一-鿿]+', q):
        tokens.update(seq[i:i+2] for i in range(len(seq) - 1))
        tokens.update(seq)  # single chars as fallback
    return [t for t in tokens if len(t) >= 2] or list(tokens)


def _score(case: dict, query: str) -> int:
    q = query.lower()
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
    score += sum(1 for t in _tokenize(q) if t in combined)
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
        return _apply_persona(persona_text, query, result)

    return result


_STALE_MONTHS = {
    "wait": 3, "escalate": 3,
    "workaround": 6,
    "tip": 9, "feature": 9,
    "pattern": 12, "client-note": 12,
}


def _months_since(date_str: str) -> int:
    try:
        if "T" in date_str:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        else:
            dt = datetime.strptime(date_str, "%Y-%m").replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        return (now.year - dt.year) * 12 + (now.month - dt.month)
    except Exception:
        return 0


def _staleness(item: dict) -> tuple:
    """Returns (age_months, threshold_months)."""
    fix_type = item.get("fix_type", "")
    threshold = _STALE_MONTHS.get(fix_type, 9)
    ref = item.get("verified_at") or item.get("last_seen", "")
    return (_months_since(ref) if ref else 0), threshold


def _frontline_score(item: dict, query: str) -> int:
    q = query.lower()
    combined = " ".join([
        item.get("issue", ""),
        item.get("fix", "") or "",
        item.get("fix_type", ""),
        " ".join(item.get("tags", [])),
        item.get("source", "") or "",
    ]).lower()
    score = 3 if q in combined else 0
    score += sum(1 for t in _tokenize(q) if t in combined)
    age, threshold = _staleness(item)
    if age >= threshold * 2:
        score = max(0, score - 3)
    elif age >= threshold:
        score = max(0, score - 1)
    return score


def _fmt_frontline(item: dict) -> str:
    fix_type = item.get("fix_type", "?")
    fix_label = {
        "wait": "放著等", "feature": "開功能", "workaround": "繞路", "escalate": "升級",
        "tip": "操作眉角", "pattern": "已知規律", "client-note": "客戶備注",
    }.get(fix_type, fix_type)
    lines = [
        f"**[{item.get('id', '?')}]** `{fix_label}`",
        f"問題：{item.get('issue', '')}",
        f"處理：{item.get('fix', '-')}",
    ]
    tags = item.get("tags", [])
    if tags:
        lines.append(f"tag：{' '.join(f'#{t}' for t in tags)}")
    age, threshold = _staleness(item)
    if age >= threshold:
        ref_label = "驗證" if item.get("verified_at") else "更新"
        lines.append(f"⚠️ {age} 個月未{ref_label}（{fix_type} 建議 {threshold} 個月內確認）")
    if item.get("verified_at"):
        lines.append(f"最後驗證：{item['verified_at'][:7]}")
    if item.get("thread_ref"):
        lines.append(f"討論串：{item['thread_ref']}")
    if item.get("source"):
        lines.append(f"頻道：{item['source']}")
    lines.append(f"最後出現：{item.get('last_seen', '-')}")
    return "\n".join(lines)


@mcp.tool()
def search_frontline(query: str, persona: Optional[str] = None) -> str:
    """Search CM frontline ops issues — quick problems, transient bugs, feature toggles. Ask in plain Chinese or English.

    persona: optional tone guide. Available: aiden_chen (default), andy_yu, kochi_chuang, howard_cheng, pineapple_wu.
    """
    with _frontline_lock:
        items = list(_frontline)

    if not items:
        return "frontline 知識庫是空的，用 add_frontline 加第一條吧。"

    scored = sorted(
        [(g, _frontline_score(g, query)) for g in items],
        key=lambda x: x[1],
        reverse=True,
    )
    top = [(g, s) for g, s in scored if s > 0][:5]

    if not top:
        result = f"找不到關於「{query}」的 frontline issue（共 {len(items)} 條）。"
    else:
        parts = [f"找到 {len(top)} 條（共 {len(items)} 條）：\n"]
        for i, (item, _) in enumerate(top, 1):
            parts.append(f"### {i}.\n{_fmt_frontline(item)}\n")
        result = "\n".join(parts)

    persona_name = persona or DEFAULT_PERSONA
    persona_text = _load_persona(persona_name)
    if persona_text:
        return _apply_persona(persona_text, query, result)

    return result


@mcp.tool()
def add_frontline(
    issue: str,
    fix_type: str,
    fix: str,
    thread_ref: str,
    tags: Optional[list] = None,
    source: Optional[str] = None,
) -> str:
    """Add a CM frontline ops issue entry.

    fix_type: 'wait' (放著等), 'feature' (開功能), 'workaround' (繞路), 'escalate' (升級),
              'tip' (操作眉角), 'pattern' (已知規律), 'client-note' (客戶備注)
    thread_ref: REQUIRED — Slack thread URL or message ts (e.g. https://appier.slack.com/archives/C.../p...)
    tags: free-form list, e.g. ['pangle', 'video', 'kr']
    source: channel name or reporter, optional
    """
    now = datetime.now(timezone.utc)
    with _frontline_lock:
        n = len(_frontline) + 1

    item = {
        "id": f"frontline-{now.strftime('%Y%m%d')}-{n:04d}",
        "issue": issue,
        "fix_type": fix_type,
        "fix": fix,
        "thread_ref": thread_ref,
        "tags": tags or [],
        "last_seen": now.strftime("%Y-%m"),
        "verified_at": now.isoformat(),
        "source": source,
    }

    with open(FRONTLINE_PATH, "a") as f:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")

    _reload_frontline()

    index = json.loads(FRONTLINE_INDEX_PATH.read_text()) if FRONTLINE_INDEX_PATH.exists() else {}
    index["last_updated"] = now.isoformat()
    index["total"] = n
    FRONTLINE_INDEX_PATH.write_text(json.dumps(index, ensure_ascii=False, indent=2))

    return f"已新增：{item['id']}\n{_fmt_frontline(item)}"


@mcp.tool()
def verify_frontline(item_id: str) -> str:
    """Mark a frontline entry as still valid. Resets the staleness clock.

    item_id: the frontline id, e.g. 'frontline-20260623-0003'
    """
    now = datetime.now(timezone.utc)
    updated = False

    with _frontline_lock:
        items = list(_frontline)

    new_items = []
    for item in items:
        if item.get("id") == item_id:
            item = dict(item)
            item["verified_at"] = now.isoformat()
            updated = True
        new_items.append(item)

    if not updated:
        return f"找不到 {item_id}。"

    with open(FRONTLINE_PATH, "w") as f:
        for item in new_items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    _reload_frontline()

    index = json.loads(FRONTLINE_INDEX_PATH.read_text()) if FRONTLINE_INDEX_PATH.exists() else {}
    index["last_updated"] = now.isoformat()
    index["total"] = len(new_items)
    FRONTLINE_INDEX_PATH.write_text(json.dumps(index, ensure_ascii=False, indent=2))

    return f"✓ {item_id} 已驗證（{now.strftime('%Y-%m-%d')}），staleness 計時重置。"


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
