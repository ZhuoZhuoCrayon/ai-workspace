---
name: dev-env
description: >
  准备和修复 Go、Node.js、Python 本地开发环境。
  用于版本切换、工具链缺失、依赖环境异常、虚拟环境问题，以及编译、测试、检查命令中的环境类失败。
---

# Dev Env

## 0x01 核心

- 在任何项目下，假定 `gvm`、`nvm`、`uv` 已经安装。
- 先运行项目命令，环境失败时再读对应 reference。

## 0x02 Reference

| 语言 | 触发线索 | 文档 |
| --- | --- | --- |
| Go | `go.mod`、Go 版本或 `gvm` 报错 | [go.md](references/go.md) |
| Node.js | `.nvmrc`、`package.json`、Node.js 或 `nvm` 报错 | [node.md](references/node.md) |
| Python | `pyproject.toml`、`uv.lock`、`.venv`、Python 或 `uv` 报错 | [python.md](references/python.md) |

## 0x03 交付证据

- 说明版本来源、目标版本和版本管理器。
- 列出实际执行命令。
- Python 项目先用 `uv`，仅在环境缺失类报错后询问是否创建或同步环境。
