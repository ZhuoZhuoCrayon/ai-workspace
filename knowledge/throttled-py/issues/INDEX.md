# throttled-py Issues 索引

| 文件 | 标签 | 摘要 | 更新日期 |
|------|------|------|---------|
| [Store 类型抽象边界优化](./2026-05-06-store-typing-abstraction-refactor/README.md) | `throttled-py` `typing` `store` `abstraction` `public-api` `sync-async` | 从底向上重画 sync / async 分界，重新定义 BaseStore 公共边界与内部执行层复用方式 | 2026-05-10 |
| [优化存储不可用时的异常处理](./2026-05-03-store-unavailable-error-handling/README.md) | `throttled-py` `store` `redis` `exception` `reliability` | 为存储后端异常提供统一的 StoreUnavailableError 包装，并以最小测试覆盖 sync / async 主路径 | 2026-05-06 |
| [mypy strict 模式合规改造](./2026-04-06-mypy-strict-compliance/README.md) | `throttled-py` `typing` `mypy` `strict` | 消除 mypy --strict 下全部 248 个类型错误，禁止 type: ignore，并通过 PR #159 收口类型边界 | 2026-04-26 |
| [throttled-py 可读容量配置 DSL 需求定义](./2026-04-04-quota-dsl-research-and-requirement/README.md) | `throttled-py` `quota` `dsl` `requirement` | 定义 quota 字符串 DSL 的需求边界与调研方法论，调研结论沉淀在 PLAN | 2026-04-05 |
| [throttled-py 半年 RoadMap 优势评估](./2026-04-04-2026h1-roadmap/README.md) | `throttled-py` `roadmap` `strategy` `product` | 记录 throttled-py 2026H1 演进 RoadMap 的核心优势与价值判断 | 2026-04-04 |
| [Release Drafter 支持 scoped conventional commits](./2026-02-22-release-drafter-scoped-commits/README.md) | `ci` `release-drafter` `dependabot` | 让 autolabeler 正确匹配 build(deps) 等带 scope 的提交标题 | 2026-02-22 |
