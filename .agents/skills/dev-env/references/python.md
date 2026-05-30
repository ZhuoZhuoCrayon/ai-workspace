# Python 环境

## 0x01 检查表

安装：缺 `uv` 时，先询问是否安装。

参考：[uv README](https://github.com/astral-sh/uv)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

版本优先级：

1. `.python-version`
2. `pyproject.toml` 的 `requires-python`
3. 用户明确指定的版本

环境规则：

- 先直接执行 `uv`，不预查 `.venv`。
- 默认 `.venv` 已存在时，`uv` 会自动发现并使用。
- `pyproject.toml` / `uv.lock` 走 `uv run` 或项目脚本。
- `requirements*.txt` 可走 `uv pip` 兼容接口。

运行：

```bash
uv run <command>
```

分支：

- 环境缺失、Python 版本缺失或依赖未同步：询问是否执行 `uv venv`、`uv sync` 或对应修复命令。
- 非项目工具：优先 `uv tool run`，必要时用 `uv run --with`。
- 禁止：不使用 `pip install --user`、全局 `pip` 或系统 Python 临时补包。

非项目工具示例：

```bash
uv tool run --from pre-commit pre-commit run --all-files
uv run --with pre-commit pre-commit run --all-files
```
