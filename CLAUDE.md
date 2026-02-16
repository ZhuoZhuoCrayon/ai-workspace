# Claude 工作区指引

本工作区使用文件系统 + Markdown 作为核心协议。请先阅读 `AGENTS.md` 了解完整的工作区结构和规范。

## 关键约定

- **并行读取**：任何项目定位或知识检索，必须第一步同时读取公开和私有两条路径，禁止只读一侧
  - 仓库：`repos.json` **+** `private/repos.json`
  - 知识：`knowledge/<project>/` **+** `private/knowledge/<project>/`
- 知识按项目隔离，存放在 `knowledge/<project>/`，跨项目通用知识在 `knowledge/_shared/`
- 处理项目任务时，从两份 repos.json 获取 `local_path`，通过 `cd` 切换到项目目录开发

## 可用 Skills

- `.cursor/skills/knowledge_mgr/SKILL.md`：知识管理（创建/归档/索引）
- `.cursor/skills/project_mgr/SKILL.md`：项目管理（添加/删除）

