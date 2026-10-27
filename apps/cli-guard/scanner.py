"""Inspect labeled text with network policy and Betterleaks; independent of any CLI."""

from __future__ import annotations

import html
import ipaddress
import json
import re
import unicodedata
from bisect import bisect_right
from dataclasses import dataclass
from typing import Any, NamedTuple
from urllib.parse import unquote

import betterleaks

Network = ipaddress.IPv4Network | ipaddress.IPv6Network
IPV4: re.Pattern[str] = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?!\w|\.\d)")
IPV6: re.Pattern[str] = re.compile(r"(?<![\w:])(?:[\da-f]{0,4}:){2,}[\da-f:.]*(?![\w:])", re.I)


class ScanError(Exception):
    """Inspection failed; callers must not treat the text as safe."""


class Finding(NamedTuple):
    field: str
    line: int
    rule: str


@dataclass(frozen=True)
class Policy:
    domains: list[re.Pattern[str]]
    block_ips: bool
    networks: list[Network]
    secrets: bool
    patterns: dict[str, str]

    @classmethod
    def from_config(cls, data: dict[str, Any]) -> Policy:
        if set(data) != {"network", "secrets"}:
            raise ValueError("unknown_or_missing_scanner_sections")
        network: dict = data["network"]
        secrets: dict = data["secrets"]
        if set(network) != {"blocked_domains", "block_ips", "allowed_ip_networks"}:
            raise ValueError("invalid_network_keys")
        if set(secrets) != {"enabled", "patterns"}:
            raise ValueError("invalid_secrets_keys")
        if type(network["block_ips"]) is not bool or type(secrets["enabled"]) is not bool:
            raise ValueError("invalid_policy_types")
        patterns: Any = secrets["patterns"]
        if not isinstance(patterns, dict):
            raise ValueError("invalid_secret_patterns")
        for name, pattern in patterns.items():
            if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{0,100}", name):
                raise ValueError("invalid_rule_name")
            if not isinstance(pattern, str) or not pattern:
                raise ValueError("invalid_rule_pattern")
        domains: list[re.Pattern[str]] = [
            re.compile(r"(?<![\w-])" + re.escape(name) + r"(?![\w-])", re.I)
            for name in strings(network["blocked_domains"])
        ]
        return cls(
            domains,
            network["block_ips"],
            [ipaddress.ip_network(value) for value in strings(network["allowed_ip_networks"])],
            secrets["enabled"],
            patterns,
        )


def strings(values: Any) -> list[str]:
    if not isinstance(values, list) or any(not isinstance(v, str) or not v for v in values):
        raise ValueError("expected_string_list")
    return values


def normalize(text: str) -> str:
    try:
        decoded: Any = json.loads(text)
    except ValueError:
        decoded = None
    if isinstance(decoded, (dict, list, str)):
        text = json.dumps(decoded, ensure_ascii=False, indent=2)
    for _ in range(3):
        text = html.unescape(unquote(text))
    return unicodedata.normalize("NFKC", text).translate(str.maketrans({"。": ".", "｡": "."}))


def check_network(text: str, policy: Policy) -> tuple[int, str] | None:
    for number, line in enumerate(text.splitlines(), 1):
        if any(domain.search(line) for domain in policy.domains):
            return number, "internal_domain"
        if not policy.block_ips:
            continue
        for candidate in IPV4.findall(line) + IPV6.findall(line):
            try:
                address = ipaddress.ip_address(candidate.rstrip("."))
            except ValueError:
                continue
            if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
                address = address.ipv4_mapped
            if not any(address in network for network in policy.networks):
                return number, "ip_address"
    return None


def inspect(values: list[tuple[str, str]], policy: Policy) -> Finding | None:
    texts: list[str] = []
    starts: list[int] = []
    next_line: int = 1
    for label, value in values:
        text: str = normalize(value)
        finding: tuple[int, str] | None = check_network(text, policy)
        if finding:
            return Finding(label, *finding)
        texts.append(text)
        starts.append(next_line)
        next_line += text.count("\n") + 1
    if policy.secrets and texts:
        try:
            finding = betterleaks.check("\n".join(texts), policy.patterns)
        except betterleaks.EngineError as error:
            raise ScanError(str(error)) from None
        if finding:
            line, rule = finding
            if not 1 <= line < next_line:
                raise ScanError("Betterleaks returned an invalid source location.")
            index: int = bisect_right(starts, line) - 1
            return Finding(values[index][0], line - starts[index] + 1, rule)
    return None
