# Claude 工作区指引

本工作区使用文件系统 + Markdown 作为核心协议。请先阅读 `AGENTS.md` 了解完整的工作区结构和规范。

## 关键约定

- 所有检索必须同时扫描公开（`knowledge/`、`projects/`）和私有（`private/knowledge/`、`private/projects/`）路径
- 知识按项目隔离，存放在 `knowledge/<project>/`，跨项目通用知识在 `knowledge/_shared/`
- 所有外部项目通过软链接接入 `projects/` 或 `private/projects/`
- 项目元信息记录在 `repos.json` / `private/repos.json`

## 可用 Skills

- `.cursor/skills/knowledge_mgr/SKILL.md`：知识管理（创建/归档/索引）
- `.cursor/skills/project_mgr/SKILL.md`：项目管理（添加/删除）
- `.cursor/skills/daily_journal/SKILL.md`：工作日志
