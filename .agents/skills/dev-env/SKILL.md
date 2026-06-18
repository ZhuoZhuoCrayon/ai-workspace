---
name: dev-env
description: >
  准备和修复 Go、Node.js、Python 本地开发环境。
  用于版本切换、工具链缺失、依赖环境异常、虚拟环境问题，以及编译、测试、检查命令中的环境类失败。
  典型信号：系统已装版本低于 `go.mod`、`.nvmrc`、`pyproject.toml` 要求，出现 `invalid go version`，找不到 `gvm`、`nvm`、`uv`，或 `uv sync` 报错。
  在判定环境不可用或跳过、假装跳过编译、测试前，必须先用本 skill 尝试切换或修复环境。
---

# Dev Env

## 0x01 核心

- 任何项目下都假定 `gvm`、`nvm`、`uv` 已装。
- `gvm`、`nvm` 是 `source` 进来的 shell 函数，`which` 查不到是正常现象，不要据此判定未安装。
- 先跑项目命令，遇到环境类失败再读对应 reference。
- 系统默认版本和项目声明版本不一致（如 `go.mod` 要 `1.23`、系统是 `1.20`）就是本 skill 的场景：先用版本管理器切到目标版本，不要判定环境不可用或跳过、假装跳过编译、测试。
- 版本管理器加载不上或行为异常时，再直连它装好的二进制兜底（见各 reference）。

## 0x02 Reference

| 语言 | 触发线索 | 文档 |
| --- | --- | --- |
| Go | `go.mod`、Go 版本或 `gvm` 报错 | [go.md](references/go.md) |
| Node.js | `.nvmrc`、`package.json`、Node.js 或 `nvm` 报错 | [node.md](references/node.md) |
| Python | `pyproject.toml`、`uv.lock`、`.venv`、Python 或 `uv` 报错 | [python.md](references/python.md) |

## 0x03 交付证据

- 说明版本来源、目标版本和版本管理器。
- 列出实际执行的命令。
