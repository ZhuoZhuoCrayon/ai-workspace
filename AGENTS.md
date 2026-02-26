# AI 工作区指引

## 工作区结构

- `repos.json` / `private/repos.json`：仓库注册表（含 `local_path`，可 `cd` 到项目目录开发）
- `knowledge/` / `private/knowledge/`：知识库（按项目隔离，含 issues、snippets、troubleshooting 等）
- `.cursor/skills/`：工作区 Skill
- `.cursor/rules/`：工作区 Rules

## 通用规范

- 使用中文进行沟通和文档撰写
- 代码注释使用英文
- 所有文档使用 Markdown 格式
- Git 提交信息遵循 Conventional Commits 规范
- 引用路径时使用完整相对路径

## 知识检索规则

**关键规则：任何涉及项目定位或知识检索的操作，必须在第一步并行读取公开和私有两条路径。禁止只读一侧后就得出「找不到」的结论。**

- 仓库：`repos.json` **+** `private/repos.json`（并行读取）
- 知识：`knowledge/<project>/` **+** `private/knowledge/<project>/`（并行扫描）

## 项目访问方式

外部项目通过 `repos.json` / `private/repos.json` 注册，其中 `local_path` 字段记录本地仓库绝对路径。

**【CRITICAL】当用户消息中提到具体项目名（如 bkm-skills、bkmonitor_mcp 等），第一步必须并行读取 `repos.json` + `private/repos.json` 获取该项目的 `local_path`，后续所有 git / 文件操作在 `local_path` 目录下执行。禁止在 ai-workspace 目录下操作其他项目的 git 仓库。**

处理项目任务时：

1. **并行读取** `repos.json` 和 `private/repos.json`，查找项目的 `local_path`
2. **切换到 `local_path`**：所有 git、代码操作使用 `working_directory: <local_path>`
3. **并行加载** `knowledge/<project>/` 和 `private/knowledge/<project>/` 作为上下文

> 注意：部分项目仅注册在 `private/repos.json` 中。如果只读 `repos.json` 会导致找不到项目。遇到「找不到项目/路径」时，先确认是否已读取两份 repos.json，再向用户确认。

## 知识继承顺序

**【CRITICAL】回答项目相关问题或执行项目任务时，必须先按以下优先级检索知识库（issues、snippets、troubleshooting 等所有对象），命中则直接引用；未命中再探索项目源码。禁止跳过知识库直接搜索源码。**

处理项目任务时，按以下优先级查找知识：

1. 会话上下文
2. 任务上下文 → `knowledge/<project>/issues/<YYYY-MM-DD-title>/`
3. 项目知识库 → `knowledge/<project>/` + `private/knowledge/<project>/`（搜索所有对象：issues、snippets、troubleshooting）
4. 项目自身 → `<local_path>/AGENTS.md`、`<local_path>/.cursor/rules/`（通过 `repos.json` 中的 `local_path` 定位）
5. 项目源码 → `<local_path>` 下的代码文件（仅在 1~4 未命中时）
6. 通用知识 → `knowledge/_shared/` + `private/knowledge/_shared/`
7. 工作区全局 → `AGENTS.md`、`.cursor/rules/`、`.cursor/skills/`

## 任务处理流程

1. 阅读 `knowledge/<project>/issues/<date-title>/README.md`
2. 查找 `knowledge/<project>/` 和 `<local_path>/AGENTS.md`（从 `repos.json` 获取 `local_path`）
3. 制定 `knowledge/<project>/issues/<date-title>/PLAN.md`
4. 执行实施
5. 更新 `knowledge/<project>/issues/<date-title>/PROGRESS.md`

