#!/usr/bin/env python3
"""检查待公开文本，先执行本地规则，再调用 PreCI 扫描确切文件。"""

from __future__ import annotations

import argparse
import hashlib
import html
import ipaddress
import json
import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import unquote

INTERNAL_DOMAIN = re.compile(r"(?<![\w.-])(?:[a-z0-9-]+\.)*(?:woa\.com|oa\.com)(?![\w-])", re.I)
IPV4 = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])")
PRIVATE_NETWORKS = tuple(ipaddress.ip_network(value) for value in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))
CREDENTIAL_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    re.compile(r"\b(?:gh[pousr]_[a-zA-Z0-9]{20,}|github_pat_[a-zA-Z0-9_]{20,})\b"),
    re.compile(r"\bAuthorization\s*:\s*(?:Bearer|Basic)\s+[a-zA-Z0-9_+/=.-]{8,}", re.I),
    re.compile(r"\b(?:app_secret|app_token|access_token|bk_ticket|password)\b[\"']?\s*[:=]\s*[\"']?([a-zA-Z0-9_+/=.-]{8,})", re.I),
    re.compile(r"\bCookie\s*:\s*\w+=[a-zA-Z0-9_+/=.-]{8,}", re.I),
)
PLACEHOLDERS = {"redacted", "placeholder", "test-token", "dummy-secret", "example-token"}


def local_findings(text: str) -> list[dict]:
    findings: list[dict] = []
    for number, raw in enumerate(text.splitlines(), 1):
        line: str = raw
        for _ in range(3):
            line = html.unescape(unquote(line))
        line = line.translate(str.maketrans({"。": ".", "．": ".", "｡": "."}))
        rules: set[str] = set()
        if INTERNAL_DOMAIN.search(line):
            rules.add("internal_domain")
        for candidate in IPV4.findall(line):
            try:
                address = ipaddress.ip_address(candidate)
            except ValueError:
                continue
            if any(address in network for network in PRIVATE_NETWORKS):
                rules.add("private_ipv4")
        for pattern in CREDENTIAL_PATTERNS:
            for match in pattern.finditer(line):
                if match.lastindex and match.group(1).lower() in PLACEHOLDERS:
                    continue
                rules.add("credential")
        findings.extend({"line": number, "rule": rule} for rule in sorted(rules))
    return findings


def check_files(paths: list[Path], project_root: Path) -> tuple[int, dict]:
    report: dict = {"status": "error", "files": [], "findings": [], "preci": []}
    originals: dict[Path, bytes] = {}
    try:
        if not project_root.is_dir():
            raise ValueError("project_root_not_directory")
        for path in paths:
            if not path.is_file():
                raise ValueError("input_not_file")
            raw: bytes = path.read_bytes()
            text: str = raw.decode("utf-8")
            if b"\x00" in raw:
                raise ValueError("input_not_text")
            originals[path] = raw
            report["files"].append({"path": str(path), "sha256": hashlib.sha256(raw).hexdigest()})
            report["findings"].extend({"file": str(path), **item} for item in local_findings(text))
    except (OSError, UnicodeError, ValueError):
        report["error"] = "invalid_input"
        return 2, report
    if report["findings"]:
        report["status"] = "blocked"
        return 1, report

    executable: str | None = shutil.which("preci")
    if executable is None:
        report["error"] = "preci_not_found"
        return 2, report
    for path in originals:
        try:
            result = subprocess.run(
                [executable, "scan", "--projectPath", str(project_root), str(path)],
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            output: str = result.stdout + result.stderr
            passed: bool = result.returncode == 0 and "localcodecheck scan not defect" in output.lower()
            report["preci"].append({"file": str(path), "returncode": result.returncode, "passed": passed})
            if not passed:
                report["error"] = "preci_not_passed"
                return 2, report
        except (OSError, subprocess.TimeoutExpired):
            report["error"] = "preci_unavailable"
            return 2, report
    try:
        if any(path.read_bytes() != raw for path, raw in originals.items()):
            report["error"] = "input_changed_during_scan"
            return 2, report
    except OSError:
        report["error"] = "input_changed_during_scan"
        return 2, report
    report["status"] = "passed"
    return 0, report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, required=True, help="PreCI 已配置的目标项目根目录")
    parser.add_argument("files", nargs="+", type=Path, help="确切待公开的 UTF-8 文本文件")
    args = parser.parse_args()
    code, report = check_files([path.resolve() for path in args.files], args.project_root.resolve())
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
