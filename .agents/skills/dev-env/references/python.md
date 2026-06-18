# Python 环境

## 0x01 准备与运行

### a. 确认 uv

缺 `uv` 时先询问是否安装。

参考 [uv README](https://github.com/astral-sh/uv)：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### b. 定位 Python 版本

按优先级取目标版本：

1. `.python-version`
2. `pyproject.toml` 的 `requires-python`
3. 用户明确指定的版本

### c. 运行规则

- 先直接执行 `uv`，不预查 `.venv`，已有 `.venv` 时 `uv` 会自动发现并使用。
- `pyproject.toml`、`uv.lock` 走 `uv run` 或项目脚本。
- 提交前检查和手动检查也走 `uv run`，避免绕开项目虚拟环境。
- `requirements*.txt` 走 `uv pip` 兼容接口。

```bash
uv run <command>                    # 例：uv run pre-commit run --files <file>
```

## 0x02 边界

### a. 版本与依赖

- 列已装 Python 用 `uv python list`，缺目标版本时询问是否 `uv python install <version>`。
- 环境缺失或依赖未同步时，询问是否执行 `uv venv`、`uv sync` 或对应修复命令。

### b. 非项目工具

优先 `uv tool run`，必要时用 `uv run --with`。

```bash
uv tool run --from pre-commit pre-commit run --all-files
uv run --with pre-commit pre-commit run --all-files
```

### c. 禁止项

不使用 `pip install --user`、全局 `pip` 或系统 Python 临时补包。
