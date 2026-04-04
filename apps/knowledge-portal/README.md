# knowledge-portal

AI 工作区知识资产可视化页面（VitePress）。

## 0x01 设计约束

- 文档发现：仅通过 `knowledge/INDEX.md`（及可用时 `private/knowledge/INDEX.md`）递归遍历 Markdown 链接发现文档。
- 项目发现：通过 `repos.json` + `private/repos.json`（兼容 `repos.yaml`）聚合项目清单。
- 禁止 hardcode 文档和项目列表。

## 0x02 本地开发

```bash
cd apps/knowledge-portal
npm install
npm run docs:dev
```

## 0x03 构建与预览

```bash
npm run docs:build
npm run docs:preview
```

构建前会自动执行 `npm run generate`，生成：

- `docs/.vitepress/sidebar.generated.json` — 侧边栏配置
- `docs/.vitepress/meta.generated.json` — 标签索引、日历数据、项目统计
- `docs/knowledge/` — 经 frontmatter 清洗的知识文档副本
- `docs/tags.md`、`docs/projects.md` — 标签与项目索引页

## 0x04 数据脚本

- 脚本：`scripts/generate-vitepress-config.mjs`
- 功能：INDEX.md BFS 遍历 → 文档发现 → frontmatter 清洗并复制 → sidebar/meta 生成 → 索引页生成
