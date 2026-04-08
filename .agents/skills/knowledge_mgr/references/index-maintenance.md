# Index Maintenance

只在需要更新索引、重建分类概览或修复知识链接时阅读本文件。

## 0x01 适用场景

- 目标侧索引更新
- 源侧索引清理
- 重建 `INDEX.md`
- 修复数量统计或相对路径链接

## 0x02 逐级更新步骤

1. 读取变更文件 frontmatter；无需先读全文。
2. 若缺少 frontmatter，先按 [operations.md](operations.md) 的字段表补全。
3. 若对应层级 `INDEX.md` 不存在，按本文件模板新建。
4. 更新对应条目的标签、摘要、日期。
5. 向上逐级重复 3-4，直到项目级或一级索引。

## 0x03 全量重建

仅在明确要求时执行：

1. 读取目标目录下所有 `.md` 的 frontmatter，排除 `INDEX.md`。
2. 按更新时间倒序重新生成当前层 `INDEX.md`。
3. 再向上逐级更新父级索引。

## 0x04 索引模板

**三级**（`knowledge/<project>/<category>/INDEX.md`）：

```markdown
# <project> <Category> 索引

| 文件 | 标签 | 摘要 | 更新日期 |
|------|------|------|---------|
| [标题](./<文件或目录>/README.md) | `tag1` `tag2` | 一句话摘要 | YYYY-MM-DD |
```

**二级**（`knowledge/<project>/INDEX.md`）：

```markdown
# <project> 知识库

> 项目一句话描述

## 索引

| 分类 | 路径 | 数量 | 说明 |
|------|------|------|------|
| Issues | [issues/](./issues/INDEX.md) | N 篇 | ... |
| 代码片段 | [snippets/](./snippets/INDEX.md) | N 篇 | ... |
```

**一级**（`knowledge/INDEX.md`）：

```markdown
# 知识库索引

> 最后更新：YYYY-MM-DD

## 项目知识

| 项目 | 路径 | 数量 | 说明 |
|------|------|------|------|
| 通用知识 | [_shared/](./_shared/INDEX.md) | N 篇 | ... |

## 最近更新

- YYYY-MM-DD：<动作> [<标题>](<相对路径>) <补充说明>
```

## 0x05 计数与最近更新约定

- 数量统计按逻辑单元计数：issue 目录合计 `1`，snippet / troubleshooting 各文件计 `1`。
- 仅统计当前可见性路径内的数量，不跨 public / private 合并。
- 最近更新保留最近 `5` 条。动作词使用：`新增`、`更新`、`归档`、`迁移`、`删除`。
