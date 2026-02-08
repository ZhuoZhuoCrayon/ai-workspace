# AI 工作区指引

## 工作区结构

- `repos.json` / `private/repos.json`：仓库注册表
- `projects/` / `private/projects/`：项目软链接（均指向本地 Git 仓库）
- `knowledge/` / `private/knowledge/`：知识库（按项目隔离）
- `issues/` / `private/issues/`：任务管理
- `.cursor/skills/`：工作区 Skill
- `.cursor/rules/`：工作区 Rules

## 通用规范

- 使用中文进行沟通和文档撰写
- 代码注释使用英文
- 所有文档使用 Markdown 格式
- Git 提交信息遵循 Conventional Commits 规范
- 引用路径时使用完整相对路径

## 知识检索规则

检索知识和仓库时，必须同时扫描公开和私有路径：

- 知识：`knowledge/` + `private/knowledge/`
- 仓库：`repos.json` + `private/repos.json`
- 项目：`projects/` + `private/projects/`
- 任务：`issues/` + `private/issues/`

## 知识继承顺序

处理项目任务时，按以下优先级查找知识：

1. 会话上下文
2. 任务上下文 → `issues/<YYYY-MM-DD-title>/`
3. 项目自身 → `projects/<project>/AGENTS.md`、`projects/<project>/.cursor/rules/`
4. 项目知识库 → `knowledge/<project>/` + `private/knowledge/<project>/`
5. 通用知识 → `knowledge/_shared/` + `private/knowledge/_shared/`
6. 工作区全局 → `AGENTS.md`、`.cursor/rules/`、`.cursor/skills/`

## 任务处理流程

1. 阅读 `issues/<date-title>/README.md`
2. 查找 `knowledge/<project>/` 和 `projects/<project>/AGENTS.md`
3. 制定 `issues/<date-title>/PLAN.md`
4. 执行实施
5. 更新 `issues/<date-title>/PROGRESS.md`
