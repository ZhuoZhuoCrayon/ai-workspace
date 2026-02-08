# project_mgr — 项目管理

管理工作区中项目的添加和删除。

## 触发方式

| 用户指令 | 执行动作 |
|---------|---------|
| "把 xxx 项目接入工作区" | 添加项目 |
| "移除 xxx 项目" | 删除项目 |

## 添加项目

### 输入参数

| 参数 | 必填 | 说明 |
|------|------|------|
| name | 是 | 项目名称（小写英文短横线） |
| local_path | 是 | 本地仓库绝对路径 |
| git_url | 是 | Git 远程仓库地址 |
| branch | 是 | 主分支名（如 main） |
| description | 否 | 项目简述 |
| visibility | 是 | public / private |

### 执行步骤

1. 验证 `local_path` 存在且是 Git 仓库
2. 创建软链接：
   - public → `ln -s <local_path> projects/<name>`
   - private → `ln -s <local_path> private/projects/<name>`
3. 追加到仓库注册表：
   - public → `repos.json`
   - private → `private/repos.json`

   条目格式：
   ```json
   {
     "name": "<name>",
     "description": "<description>",
     "git_url": "<git_url>",
     "branch": "<branch>",
     "local_path": "<local_path>"
   }
   ```
4. 初始化项目知识目录：
   - public → 创建 `knowledge/<name>/INDEX.md`
   - private → 创建 `private/knowledge/<name>/INDEX.md`
5. 检查 `projects/<name>/AGENTS.md` 是否存在，不存在则提示用户创建
6. 更新 `knowledge/INDEX.md`（或 `private/knowledge/INDEX.md`）

## 删除项目

### 输入参数

| 参数 | 必填 | 说明 |
|------|------|------|
| name | 是 | 项目名称 |
| visibility | 是 | public / private |

### 执行步骤

1. 删除软链接：
   - public → `rm projects/<name>`
   - private → `rm private/projects/<name>`
2. 从 `repos.json` 或 `private/repos.json` 中移除对应条目
3. 询问用户是否同时删除 `knowledge/<name>/`（默认保留）
4. 更新 `knowledge/INDEX.md`（或 `private/knowledge/INDEX.md`）

## 项目规范

接入的项目建议在仓库根目录包含以下文件：

| 文件 | 作用 |
|------|------|
| `AGENTS.md` | 项目级 AI 指引（技术栈、架构、约定） |
| `.cursor/rules/` | 项目级 Cursor Rules |
| `.cursor/skills/` | 项目级 Cursor Skills |
