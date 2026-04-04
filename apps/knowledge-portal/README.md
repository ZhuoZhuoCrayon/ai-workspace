# knowledge-portal

AI 工作区知识资产可视化页面（React + Vite）。

## 0x01 设计约束

- 文档发现：仅通过 `knowledge/INDEX.md`（及可用时 `private/knowledge/INDEX.md`）递归遍历 Markdown 链接发现文档。
- 项目发现：通过 `repos.json` + `private/repos.json`（兼容 `repos.yaml`）聚合项目清单。
- 禁止 hardcode 文档和项目列表。

## 0x02 本地开发

```bash
cd apps/knowledge-portal
npm install
npm run dev
```

## 0x03 构建

```bash
cd apps/knowledge-portal
npm run build
```

构建前会自动执行：

- `npm run generate:data`
- 输出文件：`apps/knowledge-portal/public/data/knowledge.json`

## 0x04 数据脚本

- 脚本：`apps/knowledge-portal/scripts/generate-knowledge-data.mjs`
- 功能：索引遍历、frontmatter 解析、文档元数据聚合、项目注册表聚合、警告输出

