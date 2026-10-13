#!/usr/bin/env python3
"""Sync workspace knowledge documents to iWiki (local -> iWiki).

Usage:
    python3 .agents/skills/iwiki-sync/scripts/sync.py <path>... [--dry-run] [--force]

``<path>`` is a knowledge entity directory (e.g. an issue folder) or a single
Markdown file under ``knowledge/`` or ``private/knowledge/``.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_MCP_URL = "https://prod.mcp.it.woa.com/app_iwiki_mcp/mcp3"
DOC_URL = "https://iwiki.woa.com/p/{docid}"
MAPPING_FILE = ".iwiki-sync.json"
ROOT_FOLDER_KEY = "AI 工作区/"
KNOWLEDGE_PREFIXES: tuple[tuple[str, ...], ...] = (("private", "knowledge"), ("knowledge",))
TITLE_BY_RELPATH: dict[str, str] = {
    "README.md": "需求",
    "PLAN.md": "实施方案",
    "PROGRESS.md": "进展",
    "REPORT.md": "调研报告",
    "validation/README.md": "实验说明",
}
SKIP_FILES = {"INDEX.md"}
SKIP_DIR_NAMES = {"__pycache__", "node_modules"}
DATE_PREFIX = re.compile(r"^(\d{4}-\d{2}-\d{2})-")
FRONTMATTER = re.compile(r"^---\n(.*?)\n---\n+", re.DOTALL)


class SyncError(RuntimeError):
    pass


class MCPClient:
    """Minimal MCP streamable-HTTP client for the iWiki server."""

    def __init__(self, url: str, headers: dict[str, str]):
        self.url: str = url
        self.headers: dict[str, str] = headers
        self.session_id: str | None = None
        self.seq: int = 0
        self._rpc(
            "initialize",
            {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "iwiki-sync", "version": "1.0"},
            },
        )
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def _post(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        headers: dict[str, str] = {
            **self.headers,
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        request = urllib.request.Request(self.url, data=json.dumps(payload).encode(), headers=headers, method="POST")
        with urllib.request.urlopen(request, timeout=300) as response:
            self.session_id = response.headers.get("Mcp-Session-Id") or self.session_id
            content_type: str = response.headers.get("Content-Type", "")
            raw: str = response.read().decode()
        if not raw.strip():
            return None
        if "text/event-stream" not in content_type:
            return json.loads(raw)
        messages: list[dict[str, Any]] = [
            json.loads(line[5:]) for line in raw.splitlines() if line.startswith("data:") and line[5:].strip()
        ]
        matched: list[dict[str, Any]] = [m for m in messages if m.get("id") == payload.get("id")]
        return (matched or messages or [None])[-1]

    def _rpc(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self.seq += 1
        response = self._post({"jsonrpc": "2.0", "id": self.seq, "method": method, "params": params})
        if response is None or "error" in response:
            raise SyncError(f"{method} failed: {response}")
        return response["result"]

    def call(self, name: str, arguments: dict[str, Any]) -> str:
        result: dict[str, Any] = self._rpc("tools/call", {"name": name, "arguments": arguments})
        text: str = "".join(c.get("text", "") for c in result.get("content", []) if c.get("type") == "text")
        if result.get("isError"):
            raise SyncError(f"{name} error: {text}")
        return text

    def get_document(self, docid: int) -> str:
        return self.call("getDocument", {"docid": str(docid)})

    def create(self, space_id: int, parent_id: int, content_type: str, title: str, body: str) -> int:
        response: str = self.call(
            "createDocument",
            {"spaceid": space_id, "parentid": parent_id, "contenttype": content_type, "title": title, "body": body},
        )
        match = re.search(r'"docid"\s*:\s*"?(\d+)', response) or re.search(r'"id"\s*:\s*"?(\d+)', response)
        if not match:
            raise SyncError(f"cannot parse docid from createDocument response: {response[:300]}")
        return int(match.group(1))

    def save(self, docid: int, title: str, body: str) -> None:
        self.call("saveDocument", {"docid": docid, "title": title, "body": body})


@dataclass
class DocPlan:
    path: Path
    key: str
    title: str
    parent_key: str
    body: str
    updated: str


@dataclass
class DocResult:
    plan: DocPlan
    action: str
    docid: int | None = None
    detail: str = ""


def find_workspace_root() -> Path:
    for candidate in [Path.cwd(), *Path.cwd().parents]:
        if (candidate / MAPPING_FILE).exists():
            return candidate
    raise SyncError(f"{MAPPING_FILE} not found from {Path.cwd()} upwards")


def load_connection(root: Path) -> tuple[str, dict[str, str]]:
    token: str | None = os.environ.get("TAI_PAT_TOKEN")
    if token:
        return DEFAULT_MCP_URL, {"Authorization": f"Bearer {token}"}
    for config_path in (Path.home() / ".cursor/mcp.json", root / ".cursor/mcp.json"):
        if not config_path.exists():
            continue
        servers: dict[str, Any] = json.loads(config_path.read_text()).get("mcpServers", {})
        for server in servers.values():
            if "app_iwiki_mcp" in server.get("url", "") and server.get("headers"):
                return server["url"], dict(server["headers"])
    raise SyncError("no iWiki credential: set TAI_PAT_TOKEN or configure iWiki in ~/.cursor/mcp.json")


def split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    match = FRONTMATTER.match(text)
    if not match:
        return {}, text
    meta: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" in line and not line.startswith((" ", "-")):
            key, value = line.split(":", 1)
            meta[key.strip()] = value.strip()
    return meta, text[match.end() :]


def first_heading(body: str) -> str | None:
    match = re.search(r"^# (.+)$", body, re.MULTILINE)
    return match.group(1).strip() if match else None


def fingerprint(text: str) -> str:
    return hashlib.sha256(re.sub(r"\s+", "", text).encode()).hexdigest()


def utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def split_knowledge_path(rel: Path) -> tuple[tuple[str, ...], list[str]]:
    for prefix in KNOWLEDGE_PREFIXES:
        if rel.parts[: len(prefix)] == prefix:
            return prefix, list(rel.parts[len(prefix) :])
    raise SyncError(f"{rel} is not under knowledge/ or private/knowledge/")


def collect_markdown(entity_dir: Path) -> tuple[list[Path], list[Path]]:
    markdown: list[Path] = []
    skipped: list[Path] = []
    for path in sorted(entity_dir.rglob("*")):
        relative_parts = path.relative_to(entity_dir).parts
        if path.is_dir() or any(p.startswith(".") or p in SKIP_DIR_NAMES for p in relative_parts):
            continue
        if path.suffix == ".md" and path.name not in SKIP_FILES:
            markdown.append(path)
        else:
            skipped.append(path)
    return markdown, skipped


def build_plans(root: Path, target: Path) -> tuple[str, str | None, str | None, list[DocPlan], list[Path]]:
    """Return (category_folder_key, entity_folder_key, entity_folder_title, doc plans, skipped files)."""
    rel: Path = target.resolve().relative_to(root.resolve())
    prefix, parts = split_knowledge_path(rel)
    if len(parts) < 3:
        raise SyncError(f"{rel} must point to an entity directory or a document under knowledge/<project>/<category>/")
    category_key = f"{ROOT_FOLDER_KEY}{parts[0]}/{parts[1]}/"

    if target.is_file() and len(parts) == 3:
        meta, body = split_frontmatter(target.read_text())
        title = meta.get("title") or first_heading(body) or target.stem
        updated = meta.get("updated") or datetime.date.fromtimestamp(target.stat().st_mtime).isoformat()
        return category_key, None, None, [DocPlan(target, rel.as_posix(), title, category_key, body, updated)], []

    entity_dir: Path = root.joinpath(*prefix, *parts[:3])
    entity_key = f"{Path(*prefix, *parts[:3]).as_posix()}/"
    readme_meta, readme_body = (
        split_frontmatter((entity_dir / "README.md").read_text()) if (entity_dir / "README.md").exists() else ({}, "")
    )
    entity_title: str = readme_meta.get("title") or first_heading(readme_body) or entity_dir.name
    date_match = DATE_PREFIX.match(entity_dir.name)
    folder_title = f"{date_match.group(1)}-{entity_title}" if date_match else entity_title

    files, skipped = collect_markdown(entity_dir)
    if target.is_file():
        files, skipped = [target], []
    plans: list[DocPlan] = []
    for path in files:
        inner: str = path.relative_to(entity_dir).as_posix()
        meta, body = split_frontmatter(path.read_text())
        title = TITLE_BY_RELPATH.get(inner) or meta.get("title") or first_heading(body) or path.stem
        updated = meta.get("updated") or datetime.date.fromtimestamp(path.stat().st_mtime).isoformat()
        plans.append(DocPlan(path, f"{entity_key}{inner}", title, entity_key, body, updated))
    return category_key, entity_key, folder_title, plans, skipped


class Syncer:
    def __init__(self, root: Path, client: MCPClient | None, force: bool):
        self.root: Path = root
        self.client: MCPClient | None = client
        self.mapping_path: Path = root / MAPPING_FILE
        self.mapping: dict[str, Any] = json.loads(self.mapping_path.read_text())
        self.mappings: dict[str, dict[str, Any]] = self.mapping["mappings"]
        conflict_mode: str = self.mapping.get("sync_policy", {}).get("conflict_mode", "manual")
        self.local_wins: bool = force or conflict_mode == "local_wins"

    def lookup(self, key: str) -> dict[str, Any] | None:
        entry = self.mappings.get(key) or self.mappings.get(key.rstrip("/"))
        return entry if entry and entry.get("status", "active") != "tombstone" else None

    def record(self, key: str, entry: dict[str, Any]) -> None:
        self.mappings[key] = {**self.mappings.get(key, {}), **entry, "last_sync_at": utc_now(), "status": "active"}
        self.mapping_path.write_text(json.dumps(self.mapping, ensure_ascii=False, indent=2) + "\n")

    def ensure_folder(self, key: str, title: str, parent_key: str) -> int | None:
        entry = self.lookup(key)
        if entry:
            return entry["docid"]
        if self.client is None:
            return None
        parent_id = self.ensure_category_chain(parent_key)
        docid = self.client.create(self.mapping["space_id"], parent_id, "FOLDER", title, " ")
        self.record(key, {"docid": docid, "type": "FOLDER", "iwiki_title": title})
        return docid

    def ensure_category_chain(self, key: str) -> int:
        """Ensure ``AI 工作区/<project>/<category>/`` style folders exist and return the docid of ``key``."""
        if key == ROOT_FOLDER_KEY:
            root_entry = self.lookup(ROOT_FOLDER_KEY)
            if not root_entry:
                raise SyncError(f"mapping {ROOT_FOLDER_KEY!r} missing, create the root folder first")
            return root_entry["docid"]
        segments: list[str] = key[len(ROOT_FOLDER_KEY) :].strip("/").split("/")
        parent_key = ROOT_FOLDER_KEY + "".join(f"{s}/" for s in segments[:-1])
        parent_id = self.ensure_category_chain(parent_key)
        entry = self.lookup(key)
        if entry:
            return entry["docid"]
        docid = self.client.create(self.mapping["space_id"], parent_id, "FOLDER", segments[-1], " ")
        self.record(key, {"docid": docid, "type": "FOLDER", "iwiki_title": segments[-1]})
        return docid

    def sync_doc(self, plan: DocPlan, parent_id: int | None) -> DocResult:
        entry = self.lookup(plan.key)
        if self.client is None:
            return DocResult(plan, "update" if entry else "create", entry["docid"] if entry else None)

        if entry is None:
            docid = self.client.create(self.mapping["space_id"], parent_id, "MD", plan.title, plan.body)
            action = "create"
        else:
            docid = entry["docid"]
            remote = self.client.get_document(docid)
            if fingerprint(remote) == fingerprint(plan.body) and entry.get("iwiki_title") == plan.title:
                self.record(plan.key, {"remote_sha256": fingerprint(remote), "last_local_updated": plan.updated})
                return DocResult(plan, "unchanged", docid, "verified")
            baseline: str | None = entry.get("remote_sha256")
            if not self.local_wins and baseline != fingerprint(remote):
                reason = "remote changed since last sync" if baseline else "no remote baseline recorded"
                return DocResult(plan, "conflict", docid, f"{reason}, rerun with --force to overwrite")
            self.client.save(docid, plan.title, plan.body)
            action = "update"

        remote = self.client.get_document(docid)
        if fingerprint(remote) != fingerprint(plan.body):
            return DocResult(plan, "failed", docid, f"readback mismatch: local {len(plan.body)} chars, remote {len(remote)} chars")
        self.record(
            plan.key,
            {
                "docid": docid,
                "type": "MD",
                "iwiki_title": plan.title,
                "last_local_updated": plan.updated,
                "remote_sha256": fingerprint(remote),
            },
        )
        return DocResult(plan, action, docid, "verified")


def link(title: str, docid: int | None) -> str:
    return f"[{title}]({DOC_URL.format(docid=docid)})" if docid else f"{title}（待创建）"


def print_report(
    folder_title: str | None, folder_id: int | None, results: list[DocResult], skipped: list[Path], root: Path, dry_run: bool
) -> None:
    counts: dict[str, int] = {}
    for result in results:
        counts[result.action] = counts.get(result.action, 0) + 1
    print("## iWiki 同步结果" + ("（dry-run，未写入）" if dry_run else ""))
    print()
    if folder_title:
        print(f"iWiki 目录：{link(folder_title, folder_id)}")
        print()
    print("| 本地文件 | iWiki 文档 | 动作 | 说明 |")
    print("| --- | --- | --- | --- |")
    for result in results:
        print(f"| `{result.plan.key}` | {link(result.plan.title, result.docid)} | {result.action} | {result.detail} |")
    print()
    print("统计：" + "、".join(f"{action} {count}" for action, count in counts.items()))
    if skipped:
        print(f"未同步的非 Markdown 文件：{len(skipped)} 个，例如 `{skipped[0].relative_to(root).as_posix()}`")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--dry-run", action="store_true", help="only print the plan, no network calls")
    parser.add_argument("--force", action="store_true", help="local wins when remote changed or has no baseline")
    args = parser.parse_args()

    root: Path = find_workspace_root()
    client: MCPClient | None = None if args.dry_run else MCPClient(*load_connection(root))
    syncer = Syncer(root, client, args.force)
    exit_code: int = 0
    for target in args.paths:
        target = target if target.is_absolute() else Path.cwd() / target
        category_key, entity_key, folder_title, plans, skipped = build_plans(root, target)
        folder_id: int | None = None
        if entity_key:
            folder_id = syncer.ensure_folder(entity_key, folder_title, category_key)
        results: list[DocResult] = []
        for plan in plans:
            parent_id: int | None = folder_id
            if not entity_key and client:
                parent_id = syncer.ensure_category_chain(category_key)
            results.append(syncer.sync_doc(plan, parent_id))
        print_report(folder_title, folder_id, results, skipped, root, args.dry_run)
        if any(r.action in {"conflict", "failed"} for r in results):
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SyncError as error:
        print(f"error: {error}", file=sys.stderr)
        sys.exit(2)
