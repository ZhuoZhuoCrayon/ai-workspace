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

## 0x03 当前范围

- 其余条目仅作为目录骨架，后续有明确规则内容时再补充。
