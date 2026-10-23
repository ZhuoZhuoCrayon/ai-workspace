# Python 规则

按类别维护 Python 规则。

## 0x01 目录

### a. 编码风格

- 1.1 缩进
- 1.2 每行最大长度
- 1.3 空白符
- 1.4 操作符
- 1.5 括号
- 1.6 空行
- 1.7 源文件编码
- 1.8 Shebang
- 1.9 模块引用(import)
- 1.10 模块中的魔术变量(dunders)
- 1.11 注释
- 1.12 文档字符串
- 1.13 类型提示
- 1.14 字符串
- 1.15 文件和 sockets
- 1.16 访问控制
- 1.17 Main
- 1.18 命名

### b. 编码规范

- 2.1 三目运算符
- 2.2 None 条件的判断
- 2.3 lambda 匿名函数
- 2.4 异常
- 2.5 条件表达式
- 2.6 True/False 布尔运算
- 2.7 列表推导式
- 2.8 函数
- 2.9 变量
- 2.10 交互式脚本交付

## 0x02 1.13 类型提示

在 Python 代码中，默认遵循以下偏好：

- 为局部变量添加显式类型注解（如 `x: int = 1`、`items: list[str] = []`）
- 为中间变量（尤其是 `dict/list` 结构）补充类型，降低阅读和维护成本
- 新增或修改代码时优先补齐类型注解，保持与既有风格一致

示例：

```python
# Preferred
query_list: list[dict[str, Any]] = super().to_unify_query_config()
field_name: str | None = query.get("field_name")
```

## 0x03 2.10 交互式脚本交付

用户要求在 Python / Django shell 中执行脚本时，默认在 `python` 代码块中直接提供完整代码，便于复制、修改和逐段执行。

- 不将整段脚本包在 `exec("""...""")`、`exec('''...''')` 或转义字符串中，除非用户明确要求这种形式。
- 代码块内不包含 `>>>`、`...` 等交互提示符，执行环境说明放在代码块外。

Good Case：

```python
cluster_ids: list[str] = ["cluster-a", "cluster-b"]
for cluster_id in cluster_ids:
    print(cluster_id)
```

Bad Case：

```python
exec("""
cluster_ids: list[str] = ["cluster-a", "cluster-b"]
for cluster_id in cluster_ids:
    print(cluster_id)
""")
```

## 0x04 当前范围

- 其余条目仅作为目录骨架，后续有明确规则内容时再补充。
