# Claude 工作区指引

本工作区使用文件系统 + Markdown 作为核心协议。开始工作前，请先阅读以下两份文档：

1. **`AGENTS.md`**：工作区完整结构、知识检索规则、任务处理流程
2. **`.cursor/rules/`**：工作区通用编码与协作规范（git、markdown、Python 类型标注、PR review 等）

## 关键约定

- **并行读取**：任何项目定位或知识检索，必须第一步同时读取公开和私有两条路径，禁止只读一侧
  - 仓库：`repos.json` **+** `private/repos.json`
  - 知识：`knowledge/<project>/` **+** `private/knowledge/<project>/`
- 知识按项目隔离，存放在 `knowledge/<project>/`，跨项目通用知识在 `knowledge/_shared/`
- **【CRITICAL】提到项目名时，第一步查 repos.json 获取 `local_path`，后续 git / 文件操作均在该目录下执行，禁止在 ai-workspace 下操作其他项目仓库**
- **【CRITICAL】回答项目问题时，必须先检索项目知识库（issues、snippets、troubleshooting 等），命中直接引用；未命中再探索源码**

