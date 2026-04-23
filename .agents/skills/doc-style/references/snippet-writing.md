# `snippet` 写作规则

## 0x01 文档职责

- `snippet` 记录可直接复用的代码片段、命令片段或协议片段。
- 目标是让读者快速拿到“何时用、怎么用、边界是什么”。

## 0x02 推荐骨架

| 章节 | 应写内容 |
| --- | --- |
| 场景 | 这段片段解决什么问题 |
| 片段 | 关键代码、命令或配置 |
| 说明 | 关键字段、参数或调用链路 |
| 边界 | 适用条件、不适用条件、易错点 |

## 0x03 写法要求

- 片段前先给一句场景判断，让读者知道是否该继续读。
- 代码片段后只解释最关键的上下文，不重复逐行翻译。
- 若片段依赖其他模块、命令或前置条件，用列表补齐。
- 若片段用于检索或导航场景，默认同时给出关键用途，而不是只给路径。

## 0x04 正反案例

### a. 先说适用场景，再给片段

Bad：

````md
## 0x02 代码片段

```python
CodeRedefinedConfigRelation.objects.bulk_create(relations)
SetCodeRedefinedRuleResource.publish_code_relabel_to_apm(bk_biz_id, app_name)
```
````

Good：

````md
## 0x01 关键信息

### a. 适用场景

批量为应用下所有服务设置返回码重定义规则，并在写入后立即刷新配置。

## 0x02 代码片段

```python
CodeRedefinedConfigRelation.objects.bulk_create(relations)
SetCodeRedefinedRuleResource.build_code_relabel_config(bk_biz_id, app_name)
SetCodeRedefinedRuleResource.publish_code_relabel_to_apm(bk_biz_id, app_name)
```
````

### b. 片段后补关键用途，不做逐行翻译

Bad：

```md
这段代码第一行是批量创建，第二行是构建配置，第三行是发布配置。
```

Good：

```md
## 0x03 说明

- `build_code_relabel_config` 负责生成最新配置。
- `publish_code_relabel_to_apm` 负责把配置下发到运行侧。
- 若只执行批量写库而不刷新，下游不会立即生效。
```
