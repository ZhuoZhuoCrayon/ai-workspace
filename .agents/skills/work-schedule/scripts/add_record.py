#!/usr/bin/env python3
"""Add schedule records to WeCom smart spreadsheet via webhook."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

try:
    import yaml

    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False

WEBHOOK_URL = "https://qyapi.weixin.qq.com/cgi-bin/wedoc/smartsheet/webhook"
MONTH_COL_RE = re.compile(r"^(\d{1,2})\s*月$")
TEXT_COLUMNS = {"需求", "备注"}
LINK_COLUMNS = {"文档/链接"}
IMAGE_COLUMNS = {"图片"}
PRIORITY_ENUM_OPTIONS = {"P0", "P1", "P2", "done"}
PROGRESS_ENUM_OPTIONS = {
    "未启动",
    "评审中",
    "暂时挂起",
    "待产品确认方案",
    "方案就绪",
    "开发中",
    "灰度中",
    "已上线发布",
    "跟进中",
}
MONTH_STATUS_OPTIONS = {"排期", "完成", "延后"}


class UserInputError(Exception):
    """User-facing input/config error."""


def _to_text_item_list(value: Any) -> list[dict[str, str]]:
    if isinstance(value, list):
        items: list[dict[str, str]] = []
        item: Any
        for item in value:
            if isinstance(item, dict) and "text" in item:
                text: str = str(item["text"])
                if text:
                    items.append({"text": text})
            elif isinstance(item, str) and item:
                items.append({"text": item})
        return items
    if isinstance(value, str) and value:
        return [{"text": value}]
    return []


def load_config(path: str) -> dict[str, Any]:
    config_path: Path = Path(path)
    if not config_path.exists():
        raise UserInputError(f"配置文件不存在: {path}")

    try:
        raw: str = config_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise UserInputError(f"读取配置文件失败: {path} ({exc})") from exc

    if config_path.suffix in (".yaml", ".yml"):
        if not _HAS_YAML:
            raise UserInputError("需要 pyyaml 来解析 yaml 配置 (pip install pyyaml)")
        try:
            parsed_yaml: Any = yaml.safe_load(raw)
        except Exception as exc:  # pragma: no cover
            raise UserInputError(f"YAML 解析失败: {exc}") from exc
        if not isinstance(parsed_yaml, dict):
            raise UserInputError("配置文件格式错误: 顶层必须是对象")
        return parsed_yaml

    try:
        parsed_json: Any = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise UserInputError(f"JSON 解析失败: {exc}") from exc
    if not isinstance(parsed_json, dict):
        raise UserInputError("配置文件格式错误: 顶层必须是对象")
    return parsed_json


def get_schedule(config: dict[str, Any], period: str | None = None) -> dict[str, Any]:
    period_key_any: Any = period if period is not None else config.get("active", "")
    period_key: str = str(period_key_any).strip()
    if not period_key:
        raise UserInputError("未指定周期且配置中无 active 字段")

    schedules_any: Any = config.get("schedules", {})
    if not isinstance(schedules_any, dict):
        raise UserInputError("配置错误: schedules 必须为对象")
    schedules: dict[str, Any] = schedules_any

    if period_key not in schedules:
        raise UserInputError(f"周期 '{period_key}' 不在配置中，可用: {list(schedules.keys())}")

    schedule_any: Any = schedules[period_key]
    if not isinstance(schedule_any, dict):
        raise UserInputError(f"周期 '{period_key}' 的配置格式错误")
    return schedule_any


def resolve_month_input_key(col_month_num: int, month_nums: list[int], months_start: int) -> int:
    # H2 兼容两种 schema：
    # 1) 列名是 1~6 月 + months_start=7（需偏移到 7~12 输入）
    # 2) 列名本身是 7~12 月（直接用 7~12 输入）
    if months_start == 7 and month_nums and max(month_nums) <= 6:
        return col_month_num + 6
    return col_month_num


def get_xun_prefix(current_day: int) -> str:
    if current_day <= 10:
        return "P1"
    if current_day <= 20:
        return "P2"
    return "P3"


def normalize_priority_enum(value: Any) -> str | None:
    text: str = str(value).strip()
    if not text:
        return None

    upper: str = text.upper()
    if upper in {"P0", "P1", "P2"}:
        return upper
    if text.lower() == "done":
        return "done"

    for prefix in ("P0", "P1", "P2"):
        if upper.startswith(prefix):
            return prefix
    if "DONE" in upper:
        return "done"
    return None


def normalize_record(record: dict[str, Any], schedule: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = dict(record)

    project_any: Any = normalized.get("项目")
    if not isinstance(project_any, str) or not project_any.strip():
        raise UserInputError("缺少必填字段: 项目。请由上游根据 SKILL.md 的项目归属规则推测后传入。")
    normalized["项目"] = project_any.strip()

    priority_raw: Any = normalized.get("优先级")
    priority_normalized: str | None = normalize_priority_enum(priority_raw)
    if priority_normalized is None:
        priority_normalized = "P0"
        print(
            f"警告: 优先级 '{priority_raw}' 不在 {sorted(PRIORITY_ENUM_OPTIONS)} 中，已默认使用 '{priority_normalized}'",
            file=sys.stderr,
        )
    normalized["优先级"] = priority_normalized

    progress_raw: Any = normalized.get("进度")
    progress_text: str = str(progress_raw).strip()
    if progress_text in PROGRESS_ENUM_OPTIONS:
        progress_normalized = progress_text
    else:
        progress_normalized = "未启动"
        print(
            f"警告: 进度 '{progress_raw}' 不在业务枚举中，已默认使用 '{progress_normalized}'",
            file=sys.stderr,
        )
    normalized["进度"] = progress_normalized

    schema_any: Any = schedule.get("schema", {})
    if not isinstance(schema_any, dict):
        raise UserInputError("配置错误: schedule.schema 必须为对象")
    schema: dict[str, str] = {str(k): str(v) for k, v in schema_any.items()}

    months_start_any: Any = schedule.get("months_start", 1)
    if not isinstance(months_start_any, int) or months_start_any not in (1, 7):
        raise UserInputError("配置错误: months_start 仅支持 1 或 7")
    months_start: int = months_start_any

    month_nums: list[int] = []
    col_name: str
    for col_name in schema.values():
        month_match: re.Match[str] | None = MONTH_COL_RE.match(col_name)
        if month_match:
            month_nums.append(int(month_match.group(1)))

    month_data_any: Any = normalized.get("月份", {})
    month_data: dict[str, list[str]] = {}
    if isinstance(month_data_any, dict):
        k: Any
        v: Any
        for k, v in month_data_any.items():
            key: str = str(k)
            if isinstance(v, list):
                month_data[key] = [str(tag) for tag in v if str(tag)]

    month_status_raw: Any = normalized.get("月份状态", "")
    month_status_text: str = str(month_status_raw).strip()
    month_status: str = "排期"
    if month_status_text in MONTH_STATUS_OPTIONS:
        month_status = month_status_text
    else:
        priority_text: str = str(normalized.get("优先级", "")).strip().lower()
        progress_text_for_month: str = str(normalized.get("进度", "")).strip()
        remark_text: str = str(normalized.get("备注", "")).strip().lower()
        if priority_text == "done" or progress_text_for_month == "已上线发布" or "完成" in remark_text or "done" in remark_text:
            month_status = "完成"
        elif progress_text_for_month == "暂时挂起" or "延后" in remark_text or "延期" in remark_text:
            month_status = "延后"

    if not month_data:
        now: dt.datetime = dt.datetime.now()
        xun_prefix: str = get_xun_prefix(now.day)
        xun_tag: str = f"{xun_prefix}-{month_status}"
        mapped_months: list[int] = [resolve_month_input_key(n, month_nums, months_start) for n in month_nums]
        target_month: int
        if now.month in mapped_months:
            target_month = now.month
        elif mapped_months:
            target_month = mapped_months[0]
            print(
                f"警告: 当前月份 {now.month} 不在该周期列中，已默认使用月份 {target_month}",
                file=sys.stderr,
            )
        else:
            target_month = now.month
        month_data = {str(target_month): [xun_tag]}
        print(f"提示: 未提供月份，已自动填充 {month_data}", file=sys.stderr)

    normalized["月份"] = month_data
    return normalized


def classify_column(col_name: str) -> str:
    if MONTH_COL_RE.match(col_name):
        return "month_tags"
    if col_name in TEXT_COLUMNS:
        return "text"
    if col_name in LINK_COLUMNS:
        return "link"
    if col_name in IMAGE_COLUMNS:
        return "image"
    return "multi_select"


def format_value(col_name: str, value: Any) -> Any:
    col_type: str = classify_column(col_name)

    if col_type == "text":
        return str(value) if value else ""

    if col_type == "link":
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            return [value]
        if isinstance(value, str) and value:
            return [{"link": value, "text": value}]
        return []

    if col_type == "image":
        if isinstance(value, list):
            return value
        return []

    if col_type == "month_tags":
        return _to_text_item_list(value)

    return _to_text_item_list(value)


def build_request_body(schedule: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    schema_any: Any = schedule.get("schema")
    if not isinstance(schema_any, dict):
        raise UserInputError("配置错误: schedule.schema 必须为对象")
    schema: dict[str, str] = {str(k): str(v) for k, v in schema_any.items()}

    months_start_any: Any = schedule.get("months_start", 1)
    if not isinstance(months_start_any, int) or months_start_any not in (1, 7):
        raise UserInputError("配置错误: months_start 仅支持 1 或 7")
    months_start: int = months_start_any

    name_to_fid: dict[str, str] = {v: k for k, v in schema.items()}

    month_fids: dict[int, str] = {}
    fid: str
    col_name: str
    for fid, col_name in schema.items():
        month_match: re.Match[str] | None = MONTH_COL_RE.match(col_name)
        if month_match:
            month_fids[int(month_match.group(1))] = fid
    month_nums: list[int] = sorted(month_fids.keys())

    values: dict[str, Any] = {}
    raw_val: Any
    for col_name, raw_val in record.items():
        if col_name == "月份":
            continue
        target_fid: str | None = name_to_fid.get(col_name)
        if target_fid is None:
            print(f"警告: 列 '{col_name}' 未在 schema 中找到，跳过", file=sys.stderr)
            continue
        values[target_fid] = format_value(col_name, raw_val)

    month_data_any: Any = record.get("月份", {})
    month_data: dict[str, list[str]] = {}
    if isinstance(month_data_any, dict):
        month_key: Any
        month_value: Any
        for month_key, month_value in month_data_any.items():
            if isinstance(month_value, list):
                month_data[str(month_key)] = [str(tag) for tag in month_value if str(tag)]

    col_month_num: int
    for col_month_num, target_fid in month_fids.items():
        input_month_num: int = resolve_month_input_key(col_month_num, month_nums, months_start)
        tags: list[str] = month_data.get(str(input_month_num), [])
        values[target_fid] = format_value(schema[target_fid], tags)

    for fid, col_name in schema.items():
        if fid in values:
            continue
        col_type: str = classify_column(col_name)
        if col_type == "text":
            values[fid] = ""
        else:
            values[fid] = []

    body: dict[str, Any] = {"schema": dict(schema), "add_records": [{"values": values}]}
    return body


def post_webhook(key: str, body: dict[str, Any]) -> dict[str, Any]:
    if not key:
        raise UserInputError("配置错误: 当前周期缺少 webhook key")

    url: str = f"{WEBHOOK_URL}?key={key}"
    payload: bytes = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req: urllib.request.Request = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp_body: str = resp.read().decode("utf-8")
            return json.loads(resp_body)
    except urllib.error.HTTPError as exc:
        error_body: str = exc.read().decode("utf-8", errors="replace")
        raise UserInputError(f"HTTP 错误 {exc.code}: {error_body}") from exc
    except urllib.error.URLError as exc:
        raise UserInputError(f"网络错误: {exc.reason}") from exc


def confirm_before_send(body: dict[str, Any]) -> None:
    print("即将发送以下请求体：")
    print(json.dumps(body, ensure_ascii=False, indent=2))
    answer: str = input("确认发送到企业微信智能表格? [y/N]: ").strip().lower()
    if answer not in {"y", "yes"}:
        raise UserInputError("用户取消发送")


def main() -> int:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(description="向企业微信智能表格新增排期记录")
    parser.add_argument("--config", required=True, help="配置文件路径 (yaml/json)")
    parser.add_argument("--record", help="记录 JSON 文件路径，省略则从 stdin 读取")
    parser.add_argument("--period", help="指定周期（覆盖配置中的 active）")
    parser.add_argument("--dry-run", action="store_true", help="仅打印请求体，不发送")
    parser.add_argument("--yes", action="store_true", help="跳过发送前确认")
    args: argparse.Namespace = parser.parse_args()

    try:
        config: dict[str, Any] = load_config(args.config)
        schedule: dict[str, Any] = get_schedule(config, args.period)

        record_text: str
        if args.record:
            try:
                record_text = Path(args.record).read_text(encoding="utf-8")
            except OSError as exc:
                raise UserInputError(f"读取记录文件失败: {args.record} ({exc})") from exc
        else:
            record_text = sys.stdin.read()

        try:
            record_any: Any = json.loads(record_text)
        except json.JSONDecodeError as exc:
            raise UserInputError(f"记录 JSON 解析失败: {exc}") from exc
        if not isinstance(record_any, dict):
            raise UserInputError("记录格式错误: 顶层必须是 JSON 对象")

        record: dict[str, Any] = normalize_record(record_any, schedule)
        body: dict[str, Any] = build_request_body(schedule, record)

        if args.dry_run:
            print(json.dumps(body, ensure_ascii=False, indent=2))
            return 0

        if not args.yes:
            confirm_before_send(body)

        key_any: Any = schedule.get("key", "")
        key: str = str(key_any)
        result: dict[str, Any] = post_webhook(key, body)
        if result.get("errcode", 0) != 0:
            print(f"接口返回错误: {json.dumps(result, ensure_ascii=False)}", file=sys.stderr)
            return 1

        print(f"新增成功: {json.dumps(result, ensure_ascii=False)}")
        return 0
    except UserInputError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
