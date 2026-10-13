---
name: iwiki-sync
title: iwiki-sync — AI 工作区与 iWiki 双向同步
description: >
  同步 AI 工作区文档到 iWiki、从 iWiki 回写本地、做日常增量对齐时使用。
  只要用户提到“同步到 iWiki”“从 iWiki 拉取”“双向更新”“补齐映射”“重传文档”“个人空间目录对齐”，都应立即使用本 Skill。
---

# iwiki-sync — AI 工作区与 iWiki 双向同步

目标：让 `knowledge/` 与 iWiki 个人空间保持可持续、可回溯、可增量的双向同步。

| 入口 | 用途 |
| --- | --- |
| `scripts/sync.py` | 本地 -> iWiki 上传，含映射回写、冲突检测和回读校验 |
| MCP Server `user-iWiki` | 下载、目录巡检和脚本未覆盖的单点操作 |

## 0x00 前置约束

1. 同步范围从 `knowledge/<project>/` 或 `private/knowledge/<project>/` 开始，不同步整个仓库。
2. 只同步 Markdown：`INDEX.md`、代码、实验结果和 docx 等附件不上传。
3. 所有路径使用工作区根目录相对路径。
4. 同步前必须先读取 `.iwiki-sync.json`。
5. 调用 iWiki MCP 工具前，必须先用 `GetDynamicTools` 读取对应工具 schema。

## 0x01 映射文件规范

位置：工作区根目录 `.iwiki-sync.json`（已被 `.gitignore` 忽略）。

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
    "AI 工作区/bkmonitor/issues/": {
      "docid": 4018554737,
      "type": "FOLDER"
    },
    "knowledge/bkmonitor/issues/2026-03-03-apm-shared-datasource/": {
      "docid": 4018554741,
      "type": "FOLDER",
      "iwiki_title": "2026-03-03-APM 支持跨应用共享数据源",
      "status": "active"
    },
    "knowledge/bkmonitor/issues/2026-03-03-apm-shared-datasource/README.md": {
      "docid": 4018554751,
      "type": "MD",
      "iwiki_title": "需求",
      "last_local_updated": "2026-03-03",
      "last_sync_at": "2026-03-08T12:30:00Z",
      "remote_sha256": "de59ac11⋯⋯",
      "status": "active"
    }
  }
}
```

| 字段 | 说明 |
| --- | --- |
| `space_id` / `homepage_id` | iWiki 空间与首页定位 |
| `sync_policy.conflict_mode` | `manual`（默认）、`local_wins` 或 `remote_wins` |
| `sync_policy.deletion_mode` | 固定为 `tombstone`，只标记删除，不删除远端 |
| `mappings` 键 | 目录骨架用 `AI 工作区/<project>/<category>/`，实体目录和文档用本地相对路径 |
| `mappings[*].last_local_updated` | 本地 frontmatter 的 `updated`，缺失时取文件修改日期 |
| `mappings[*].remote_sha256` | 上次同步后远端正文去空白的 SHA-256，冲突检测的基线 |
| `mappings[*].status` | `active` 或 `tombstone` |

## 0x02 命名与目录映射

目录骨架固定为 `AI 工作区` → `<project>` → `<category>` → 实体目录。实体目录内的 Markdown 平铺为同级文档。

| 本地对象 | iWiki 标题 |
| --- | --- |
| 实体目录，例如 issue | `{目录名日期}-{README.md frontmatter.title}` |
| `README.md` | 需求 |
| `PLAN.md` | 实施方案 |
| `PROGRESS.md` | 进展 |
| `REPORT.md` | 调研报告 |
| `validation/README.md` | 实验说明 |
| 其他 Markdown，或分类下的单篇文档 | frontmatter `title`，缺失时取一级标题 |

- *上传正文时去掉 YAML frontmatter，远端文档从一级标题开始。*

示例：本地 `knowledge/bkmonitor/issues/2026-03-03-apm-shared-datasource/` 对应 iWiki 目录 `2026-03-03-APM 支持跨应用共享数据源`。

## 0x03 上传流程（本地 -> iWiki）

上传统一使用 `scripts/sync.py`。正文直接从文件读取，不经过模型传参，长文档不会截断。

```bash
# 1. 预览计划，不发起网络请求
python3 .agents/skills/iwiki-sync/scripts/sync.py <实体目录或文件>... --dry-run

# 2. 执行同步
python3 .agents/skills/iwiki-sync/scripts/sync.py <实体目录或文件>...

# 3. 用户确认本地覆盖远端后，处理冲突项
python3 .agents/skills/iwiki-sync/scripts/sync.py <冲突文件> --force
```

执行顺序：

1. 先跑 `--dry-run`，确认待创建、待更新的文档与用户意图一致。
2. 计划里出现用户未提及的新建项时，先问用户再执行。
3. 执行同步后，把脚本输出的结果表原样带入汇报。
4. 退出码为 `1` 时存在 `conflict` 或 `failed`，按 `0x05` 处理，不自行加 `--force`。

脚本对每篇文档的处理：

| 映射状态 | 远端状态 | 动作 |
| --- | --- | --- |
| 无映射 | — | `createDocument` 新建，缺失的父目录逐级补建 |
| 有映射 | 正文与本地一致 | `unchanged`，补记 `remote_sha256` |
| 有映射 | 指纹等于 `remote_sha256` | `saveDocument` 全量更新 |
| 有映射 | 指纹不同或无基线 | `conflict`，不写入 |

- *每次写入后脚本都会 `getDocument` 回读，比对去空白后的正文，不一致时标记 `failed`。*
- *每次创建或更新后立即回写 `.iwiki-sync.json`，中途失败也不丢映射。*

凭据读取顺序：环境变量 `TAI_PAT_TOKEN`，然后是 `~/.cursor/mcp.json` 中 URL 含 `app_iwiki_mcp` 的服务配置。

## 0x04 下载流程（iWiki -> 本地）

1. 根据 `.iwiki-sync.json` 取目标 `docid`。
2. 调用 `getDocument` 获取远端正文。
3. 保留本地原有 frontmatter，用远端正文替换其后的内容，并更新 `updated`。
4. 更新映射项的 `last_sync_at` 和 `remote_sha256`。

适用场景：

- 用户在 iWiki 手动修正文档后，需要回写本地。
- 本地文件丢失，需要从 iWiki 恢复。

## 0x05 冲突与删除策略

### a. 冲突识别

远端正文指纹与映射里的 `remote_sha256` 不同，说明上次同步后远端被改过，判定为冲突。没有 `remote_sha256` 的旧映射无法判断远端是否被改，同样按冲突处理。

### b. 冲突处理

| `conflict_mode` | 处理方式 |
| --- | --- |
| `manual`（默认） | 停止覆盖，向用户展示冲突文档链接，由用户选择来源 |
| `local_wins` | 本地覆盖远端，等价于 `--force` |
| `remote_wins` | 按 `0x04` 用远端覆盖本地 |

### c. 删除处理

iWiki MCP 没有 `deleteDocument`，不执行物理删除：

- 本地删除时，映射状态改为 `tombstone`。
- 可选：远端文档重命名为 `[已归档] <title>`，供人工清理。

## 0x06 API 实战约束

| 工具 | 约束 |
| --- | --- |
| `createDocument` | `body` 必须非空，FOLDER 传 `" "`；成功响应形如 `创建成功:{"id":…,"docid":…}` |
| `saveDocument` | `docid` 为数字，`body` 必须非空，只改标题也要传完整正文 |
| `getDocument` | `docid` 必须传字符串，返回不含标题的 Markdown 正文 |
| 删除 | 没有 `deleteDocument`，走 tombstone 或归档 |

- *直接用 MCP 工具内联传正文时，超过约 `10,000` 字符容易被截断或改写，长文档必须走脚本。*

## 0x07 日常巡检清单

每次同步后执行：

1. 抽样检查 iWiki 目录层级是否符合命名规范。
2. 对比同步文件数与 `mappings` 活跃条目数。
3. 检查是否存在“本地有文件但无 mapping”的漏同步项。
4. 检查是否存在“mapping 有 docid 但远端不可读”的失效项。
5. 记录本次同步摘要：新增、更新、未变更、冲突和 tombstone 数。

## 0x08 汇报模板

【CRITICAL（必须执行，不可协商）】汇报第一句必须给出 iWiki 目录链接，每篇文档都要带链接，链接格式为 `https://iwiki.woa.com/p/<docid>`。

```md
已同步到 iWiki：[<目录标题>](https://iwiki.woa.com/p/<目录 docid>)，新增 N、更新 N、未变更 N、冲突 N。

| 本地文件 | iWiki 文档 | 动作 |
| --- | --- | --- |
| `README.md` | [需求](https://iwiki.woa.com/p/<docid>) | create |
```

表格后按需补充：

- 失败或冲突项：文档链接、原因和建议动作。
- 映射状态：`.iwiki-sync.json` 是否已更新。
- 未同步内容：跳过的非 Markdown 文件数量及原因。
