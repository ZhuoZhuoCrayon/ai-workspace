# Operations Guide

只在知识资产写操作场景阅读本文件。涉及索引更新、重建或修复链接时，再补读 [index-maintenance.md](index-maintenance.md)。

下文将 issue、plan、snippet、troubleshooting 统称为“知识对象”。

## 0x01 适用场景

当任务涉及以下任一动作时，读取本文件：

- 创建知识对象
- 更新已有知识文档
- 归档 `knowledge/_inbox/` 或 `private/knowledge/_inbox/`
- 在 public / private 之间迁移知识对象
- 删除知识对象
- 维护索引、修复链接或重建分类概览

## 0x02 命名与 Frontmatter

命名规则：

- 仅使用小写字母、数字与短横线，禁止空格与下划线。
- 中文标题需转写为英文短语或稳定拼音，确保可读且稳定。
- 避免无意义缩写，优先表达问题域或功能点。

所有知识文件必须包含以下 frontmatter 字段：

| 字段 | 必填 | 适用对象 | 说明 |
|------|------|----------|------|
| title | 是 | 全部 | 文档标题 |
| tags | 是 | 全部 | 标签数组，如 `[k8s, ops]` |
| description | 是 | 全部 | 一句话摘要 |
| language | 否 | snippet | 代码语言 |
| issue | 否 | plan | 关联 issue 路径 |
| created | 是 | 全部 | 创建日期，`YYYY-MM-DD` |
| updated | 是 | 全部 | 最后更新日期，`YYYY-MM-DD` |

## 0x03 对象生命周期

### a. 创建

1. 确认标题、关联项目、visibility。
2. 判断可见性：涉及个人或敏感信息用 `private`，其余用 `public`。
3. 按 [templates.md](templates.md) 创建知识对象。
4. 若创建的是 plan，先读取关联 issue 的 `README.md`，并补齐相关知识证据。

### b. 更新

1. 读取目标文件与相关上下文。
2. 修改内容并保持结构完整。
3. 同步维护 frontmatter，至少检查 `updated` 与 `tags`。
4. 执行后置检查。

### c. 归档（Inbox）

1. 读取 inbox 文档，判断项目归属与对象类型。
2. 补全 frontmatter：`title`、`tags`、`description`、`created`、`updated`。
3. 移动到目标位置。
4. 删除 inbox 源文件。
5. 执行后置检查。

### d. 迁移（可见性变更）

1. 确认源文件存在，目标路径无同名冲突。
2. 移动到目标可见性路径；issue 需整目录迁移。
3. 同时做目标侧索引更新与源侧索引清理。
4. 执行一致性自检。

### e. 删除

1. 确认删除目标。
2. 删除文件或目录。
3. 执行源侧索引清理与一致性自检。

## 0x04 后置检查

任何知识资产写操作完成后，逐项执行：

1. **Frontmatter 维护**：确保 `updated` 为当天日期，`tags` 与内容一致。
2. **目标侧索引更新**：从变更文件的当前位置向上逐级更新索引。
3. **源侧索引清理**：仅迁移或删除时执行，从原位置向上逐级移除旧条目并更新数量。
4. **一致性自检**：
   - 索引中的标签、摘要、日期与文件 frontmatter 一致。
   - 各级索引数量与下级实际条目数一致。
   - 所有相对路径链接都指向实际存在的文件。

索引更新、全量重建、模板与计数约定见 [index-maintenance.md](index-maintenance.md)。
