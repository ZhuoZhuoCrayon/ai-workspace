#!/usr/bin/env bash
# 安装缺失的 WeCom CLI；版本与授权检查由官方技能在使用时执行。

set -euo pipefail

if ! command -v wecom-cli >/dev/null 2>&1; then
	npm install -g @wecom/cli
fi

wecom-cli --version
echo "wecom: if authorization is required, run: wecom-cli auth init --noninteractive"
