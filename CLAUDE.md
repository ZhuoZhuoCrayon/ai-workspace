# Claude 工作区指引

本工作区使用文件系统 + Markdown 作为核心协议。请先阅读 `AGENTS.md` 了解完整的工作区结构和规范。

## 关键约定

- 所有检索必须同时扫描公开（`knowledge/`）和私有（`private/knowledge/`）路径
- 知识按项目隔离，存放在 `knowledge/<project>/`，跨项目通用知识在 `knowledge/_shared/`
- 外部项目通过 `repos.json` / `private/repos.json` 注册，`local_path` 字段记录本地仓库路径
- 处理项目任务时，读取 `repos.json` 获取 `local_path`，通过 `cd` 切换到项目目录开发，同时加载 `knowledge/<project>/` 知识库

## 可用 Skills

- `.cursor/skills/knowledge_mgr/SKILL.md`：知识管理（创建/归档/索引）
- `.cursor/skills/project_mgr/SKILL.md`：项目管理（添加/删除）

