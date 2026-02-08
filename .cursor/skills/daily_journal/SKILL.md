# daily_journal — 工作日志

创建每日工作日志，汇总当天的开发活动。

## 触发方式

用户说"写今天的工作日志"或"记录今天的工作"。

## 执行步骤

1. 创建日志文件：`private/journal/<YYYY-MM-DD>.md`
2. 汇总当天活动：
   - 扫描 `projects/` 和 `private/projects/` 下各项目的 `git log --since=today`
   - 检查 `issues/` 和 `private/issues/` 中当天有变更的任务
   - 检查 `knowledge/` 和 `private/knowledge/` 中当天新增/更新的文档
3. 按以下格式生成日志：

```markdown
# <YYYY-MM-DD> 工作日志

## 代码提交

| 项目 | 提交 | 说明 |
|------|------|------|
| project-a | abc1234 | fix: xxx |

## 任务进度

| 任务 | 状态 | 备注 |
|------|------|------|
| issues/2026-02-08-xxx | 进行中 | 完成了方案设计 |

## 知识更新

| 文件 | 类型 | 说明 |
|------|------|------|
| knowledge/project-a/snippets/xxx.md | 新增 | xxx |

## 备注

（由用户补充）
```

4. 写入文件
