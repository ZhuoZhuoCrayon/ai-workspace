---
title: Grafana 仪表盘导入
tags: [grafana, dashboard, import]
description: 在 Django shell 中导入 Grafana 仪表盘的代码片段
language: python
created: 2026-02-09
updated: 2026-05-22
---

# Grafana 仪表盘导入

## 0x01 关键信息

### a. 适用场景

在 Django shell 中为业务导入预置的 Grafana 仪表盘。

片段包含两种用法：

- 已知单个 `bk_biz_id` 时，快速导入指定仪表盘。
- 需要从已有「BKCI-构建机」仪表盘反查负数业务时，批量补录新增仪表盘。

## 0x02 代码片段

### a. 单业务导入指定 BKCI 仪表盘

已知 `bk_biz_id` 时使用，核心入口是 `QuickImportDashboard().request()`。

```python
from monitor_web.grafana.resources.manage import QuickImportDashboard

bk_biz_id = -4219865

dash_names = [
    "bkci/BKCI-构建资源趋势.json",
    "bkci/BKCI-流水线运行趋势.json",
    "bkci/BKCI-运行中的任务.json",
    "bkci/BKCI-制品趋势.json",
]

for dash_name in dash_names:
    QuickImportDashboard().request({"bk_biz_id": bk_biz_id, "dash_name": dash_name})
```

### b. 按已有 BKCI 构建机仪表盘批量导入新增仪表盘

适合批量补录 BKCI 仪表盘：先通过已有「BKCI-构建机」仪表盘定位 org，再从 `Org.name` 反查负数业务。

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

from django.db import close_old_connections

from bk_dataview import models
from monitor_web.grafana.resources.manage import QuickImportDashboard


SOURCE_DASHBOARD_TITLE = "BKCI-构建机"
CONCURRENCY = 8
PROGRESS_INTERVAL = 160

DASH_NAMES = [
    "bkci/BKCI-构建资源趋势.json",
    "bkci/BKCI-流水线运行趋势.json",
    "bkci/BKCI-运行中的任务.json",
    "bkci/BKCI-制品趋势.json",
]


def parse_negative_bk_biz_id(org_name):
    if not org_name:
        return None

    try:
        bk_biz_id = int(str(org_name).strip())
    except ValueError:
        return None

    return bk_biz_id if bk_biz_id < 0 else None


def chunks(items, size):
    for index in range(0, len(items), size):
        yield items[index : index + size]


def import_one_biz(bk_biz_id):
    close_old_connections()
    try:
        importer = QuickImportDashboard()
        for dash_name in DASH_NAMES:
            importer.request({"bk_biz_id": bk_biz_id, "dash_name": dash_name})
        return bk_biz_id, True, ""
    except Exception as e:
        return bk_biz_id, False, f"{type(e).__name__}: {e}"
    finally:
        close_old_connections()


org_ids = (
    models.Dashboard.objects.filter(title=SOURCE_DASHBOARD_TITLE)
    .values_list("org_id", flat=True)
    .distinct()
)

bk_biz_ids = sorted(
    {
        bk_biz_id
        for bk_biz_id in (
            parse_negative_bk_biz_id(org_name)
            for org_name in models.Org.objects.filter(id__in=org_ids).values_list("name", flat=True)
        )
        if bk_biz_id is not None
    }
)

total = len(bk_biz_ids)
processed = 0
success = 0
failed = []

print(f"found {total} target bk_biz_ids, concurrency={CONCURRENCY}")

with ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
    for batch in chunks(bk_biz_ids, CONCURRENCY):
        future_map = {executor.submit(import_one_biz, bk_biz_id): bk_biz_id for bk_biz_id in batch}

        for future in as_completed(future_map):
            try:
                bk_biz_id, ok, error = future.result()
            except Exception as e:
                bk_biz_id = future_map[future]
                ok = False
                error = f"{type(e).__name__}: {e}"

            processed += 1
            if ok:
                success += 1
            else:
                failed.append((bk_biz_id, error))

            if processed % PROGRESS_INTERVAL == 0 or processed == total:
                print(f"progress: {processed}/{total}, success={success}, failed={len(failed)}")

if failed:
    print("failed bk_biz_ids:", [bk_biz_id for bk_biz_id, _ in failed])
    print("failed details:")
    for bk_biz_id, error in failed:
        print(f"  {bk_biz_id}: {error}")
else:
    print("all done, no failed bk_biz_ids")
```

关键参数：

- `CONCURRENCY = 8` 表示同时处理 `8` 个业务。
- `PROGRESS_INTERVAL = 160` 表示每处理 `160` 个业务输出一次进度。
- `failed` 统一记录业务内部任意仪表盘导入失败的业务 ID 和异常。
- 线程内通过 `close_old_connections()` 规避 Django 数据库连接在线程复用时的陈旧连接问题。
