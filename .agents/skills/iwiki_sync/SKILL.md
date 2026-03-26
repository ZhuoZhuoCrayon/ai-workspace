---
name: iwiki-sync
title: iwiki_sync — AI 工作区与 iWiki 双向同步
description: 同步 AI 工作区文档到 iWiki、从 iWiki 回写本地、做日常增量对齐时使用。只要用户提到“同步到 iWiki”“从 iWiki 拉取”“双向更新”“补齐映射”“重传文档”“个人空间目录对齐”，都应立即使用本 Skill。
---

# iwiki_sync — AI 工作区与 iWiki 双向同步

目标：让 `knowledge/` 与 iWiki 个人空间保持可持续、可回溯、可增量的双向同步。

MCP Server：`user-iWiki`

## 0x00 前置约束

1. 同步范围默认从 `knowledge/<project>/` 开始，不直接同步整个仓库。
2. `INDEX.md` 默认不同步（仅同步 issue 实体文档）。
3. 所有路径使用工作区根目录相对路径。
4. 同步前必须先读取 `.iwiki-sync.json`。
5. 调用任何 iWiki MCP 工具前，必须先读取对应工具 schema（`mcps/user-iWiki/tools/*.json`）。

## 0x01 映射文件规范

位置：工作区根目录 `.iwiki-sync.json`（应被 `.gitignore` 忽略）。

建议结构：

```json
{
  "space_id": 136740934,
  "homepage_id": 135057649,
  "root_title": "AI 工作区",
  "sync_policy": {
    "index_sync": false,
    "conflict_mode": "manual",
    "deletion_mode": "tombstone"
  },
  "mappings": {
    "knowledge/bkmonitor/issues/2026-03-03-apm-shared-datasource/README.md": {
      "docid": 4018554751,
      "type": "MD",
      "iwiki_title": "需求",
      "last_local_updated": "2026-03-03",
      "last_sync_at": "2026-03-08T12:30:00Z",
      "status": "active"
    }
  }
}
```

字段说明：

- `space_id` / `homepage_id`: iWiki 定位信息。
- `root_title`: iWiki 顶层目录名，固定为 `AI 工作区`。
- `sync_policy.conflict_mode`: `manual | local_wins | remote_wins`。
- `sync_policy.deletion_mode`: 推荐 `tombstone`（标记删除，不做远端删除）。
- `mappings[*].status`: `active | tombstone`。

## 0x02 命名与目录映射

目录骨架固定为：`AI 工作区` → `<project>` → `<category>`。

命名规则：

- issue 文件夹：`{date}-{frontmatter.title}`。
- `README.md` → `需求`。
- `PLAN.md` → `实施方案`。
- `PROGRESS.md` → `进展`。
- `INDEX.md`：默认不同步。

示例：

- 本地 `knowledge/bkmonitor/issues/2026-03-03-apm-shared-datasource/`
- iWiki 标题 `2026-03-03-APM 支持跨应用共享数据源`

## 0x03 上传流程（本地 -> iWiki）

1. 读取 `.iwiki-sync.json`，确认 `space_id`、`homepage_id` 与 `root_title`。
2. 扫描本地目录，过滤掉 `INDEX.md`。
3. 对每个条目按映射判断：
   - 无映射：新增（`createDocument`）。
   - 有映射：更新（`saveDocument`）。
4. 新增时先确保父目录存在，再创建子目录/文件。
5. 每次创建或更新后立即回写 `.iwiki-sync.json`。

新增操作规范：

- FOLDER：`contenttype="FOLDER"`，`body` 传 `" "`。
- MD：`contenttype="MD"`，`body` 传完整 Markdown。

更新操作规范：

- 使用 `saveDocument(docid, title, body)`。
- 即使只改标题，也传非空 `body`。

## 0x04 下载流程（iWiki -> 本地）

1. 根据 `.iwiki-sync.json` 取目标 `docid`。
2. 调用 `getDocument` 获取远端正文。
3. 写回本地对应路径（不存在则创建）。
4. 更新映射项中的 `last_sync_at` 与状态字段。

适用场景：

- 用户在 iWiki 手动修正文档后，需要回写本地。
- 本地文件丢失，需要从 iWiki 恢复。

## 0x05 冲突与删除策略

### a. 冲突识别

当“本地 updated 晚于 last_sync_at”且“远端也发生变更”时，判定为冲突。

### b. 冲突处理

- `manual`（默认）：停止自动覆盖，提示用户选择来源。
- `local_wins`：本地覆盖远端。
- `remote_wins`：远端覆盖本地。

### c. 删除处理

由于无 `deleteDocument` API，不执行物理删除：

- 本地删除时，将映射状态改为 `tombstone`。
- 可选：远端文档重命名为 `[已归档] <title>`，用于人工清理。

## 0x06 API 实战约束（已验证）

- `createDocument` 与 `saveDocument` 在当前环境下都应传非空 `body`。
- FOLDER 也要传 `body: " "`。
- 长文档直接内联调用容易 JSON 截断，建议分批或使用 Task 子任务执行。
- 无 `deleteDocument`，删除需走 tombstone/归档策略。

## 0x07 日常巡检清单

每次同步后执行：

1. 抽样检查 iWiki 目录层级是否符合命名规范。
2. 对比同步文件数与 `mappings` 活跃条目数。
3. 检查是否存在“本地有文件但无 mapping”的漏同步项。
4. 检查是否存在“mapping 有 docid 但远端不可读”的失效项。
5. 记录本次同步摘要（新增/更新/冲突/tombstone 数）。

## 0x08 输出模板（给用户）

同步任务结束后按以下结构汇报：

- 同步方向：本地 -> iWiki / iWiki -> 本地 / 双向
- 处理结果：新增 N、更新 N、冲突 N、tombstone N
- 失败项：列出路径 + 原因 + 建议重试动作
- 映射状态：`.iwiki-sync.json` 是否已更新
- 后续建议：是否需要执行一次全量巡检
