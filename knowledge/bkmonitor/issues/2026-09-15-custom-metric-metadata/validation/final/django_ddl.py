#!/usr/bin/env python3
"""用 Django 4.2.27（与 bk-monitor 一致）的 MySQL schema editor 生成终版三张新表与 TimeSeriesScope 迁移的 SQL。

只收集 SQL、不执行；连接目标库只为让 Django 读取服务端版本。输出写到 results/django_ddl_<tag>.sql。

运行：uv run --with 'django==4.2.27' --with 'pymysql==1.1.1' django_ddl.py <tag>
环境变量：MYSQL_HOST、MYSQL_PORT（默认 127.0.0.1:33341）
"""

import os
import sys

import pymysql

HOST, PORT = os.environ.get("MYSQL_HOST", "127.0.0.1"), int(os.environ.get("MYSQL_PORT", "33341"))
_c = pymysql.connect(host=HOST, port=PORT, user="root", password="", autocommit=True)
_c.cursor().execute("DROP DATABASE IF EXISTS djddl")
_c.cursor().execute("CREATE DATABASE djddl DEFAULT CHARACTER SET utf8")
_c.close()
pymysql.install_as_MySQLdb()

import django  # noqa: E402
from django.conf import settings  # noqa: E402

settings.configure(
    DATABASES={
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "HOST": HOST,
            "PORT": PORT,
            "USER": "root",
            "PASSWORD": "",
            "NAME": "djddl",
        }
    },
    INSTALLED_APPS=[],
    USE_TZ=False,
)
django.setup()

from django.db import connection, models  # noqa: E402
from django.db.backends.mysql.base import DatabaseWrapper  # noqa: E402
from django.db.migrations import operations as ops  # noqa: E402
from django.db.migrations.state import ProjectState  # noqa: E402

# Django 4.2 官方只支持 MySQL 8.0.11+，bk-monitor 在 5.7 上运行，这里同样跳过版本校验
DatabaseWrapper.check_database_version_supported = lambda self: None

UTF8 = "utf8_bin"
ASCII = "ascii_bin"


class MediumBlobField(models.BinaryField):
    """Django BinaryField 在 MySQL 上固定为 longblob，MEDIUMBLOB 需要自定义 db_type。"""

    def db_type(self, connection):
        return "mediumblob"


SCOPE_FIELDS = [
    ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
    ("group_id", models.IntegerField(db_index=True, verbose_name="自定义时序数据源ID")),
    ("scope_name", models.CharField(db_collation="utf8_bin", max_length=255, verbose_name="指标分组名")),
    ("dimension_config", models.JSONField(default=dict, verbose_name="分组下的维度配置")),
    ("auto_rules", models.JSONField(default=list, verbose_name="自动分组的匹配规则列表")),
    (
        "create_from",
        models.CharField(
            choices=[("data", "数据自动创建"), ("user", "用户手动创建"), ("default", "默认分组")],
            db_index=True,
            default="data",
            max_length=10,
            verbose_name="创建来源",
        ),
    ),
    ("last_modify_time", models.DateTimeField(auto_now=True, verbose_name="最后更新时间")),
]

NEW_MODELS = [
    ops.CreateModel(
        name="TimeSeriesReportValue",
        fields=[
            ("id", models.BigAutoField(primary_key=True, serialize=False)),
            ("group_id", models.IntegerField()),
            ("field_name", models.CharField(max_length=255, db_collation=UTF8)),
            ("fingerprint", models.CharField(max_length=32, db_collation=ASCII)),
            ("original_name", models.CharField(max_length=255, db_collation=UTF8)),
            ("original_type", models.CharField(max_length=16)),
            ("metric_type", models.CharField(max_length=16)),
            ("meta", models.JSONField(null=True)),
            ("scope_count", models.IntegerField(default=0)),
        ],
        options={
            "unique_together": {("group_id", "field_name", "fingerprint")},
            "indexes": [
                models.Index(fields=["group_id", "original_name"], name="tsrv_group_original_idx"),
                models.Index(fields=["group_id", "scope_count"], name="tsrv_group_count_idx"),
            ],
        },
    ),
    ops.CreateModel(
        name="TimeSeriesReportScope",
        fields=[
            ("id", models.BigAutoField(primary_key=True, serialize=False)),
            ("group_id", models.IntegerField()),
            ("scope_hash", models.CharField(max_length=32, db_collation=ASCII)),
            ("scope_type", models.CharField(max_length=32)),
            ("labels", models.JSONField(null=True)),
            ("raw_scope", models.CharField(max_length=512)),
            ("report_value_ids", MediumBlobField()),
            ("value_count", models.IntegerField(default=0)),
            ("last_seen", models.DateTimeField()),
            ("version", models.IntegerField(default=0)),
        ],
        options={
            "unique_together": {("group_id", "scope_hash")},
            "indexes": [models.Index(fields=["group_id", "last_seen"], name="tsrs_group_seen_idx")],
        },
    ),
    ops.CreateModel(
        name="TimeSeriesMetricOverride",
        fields=[
            ("id", models.BigAutoField(primary_key=True, serialize=False)),
            ("group_id", models.IntegerField()),
            ("selector_hash", models.CharField(max_length=32, db_collation=ASCII)),
            ("selector", models.JSONField(null=True)),
            ("field_name", models.CharField(max_length=255, db_collation=UTF8)),
            ("field_config", models.JSONField(null=True)),
            ("scope_id", models.IntegerField(null=True)),
        ],
        options={"unique_together": {("group_id", "selector_hash", "field_name")}},
    ),
]

SCOPE_CREATE = ops.CreateModel(
    name="TimeSeriesScope",
    fields=SCOPE_FIELDS,
    options={"unique_together": {("group_id", "scope_name")}},
)

SCOPE_MIGRATION = [
    ops.AddField("TimeSeriesScope", "selector", models.JSONField(null=True)),
    ops.AddField("TimeSeriesScope", "selector_hash", models.CharField(max_length=32, default="", db_collation=ASCII)),
    ops.AlterUniqueTogether("TimeSeriesScope", {("group_id", "selector_hash", "scope_name")}),
]


def collect(state, operations, execute=False):
    with connection.schema_editor(collect_sql=not execute, atomic=False) as editor:
        for op in operations:
            new = state.clone()
            op.state_forwards("metadata", new)
            op.database_forwards("metadata", editor, state, new)
            state = new
    return state, getattr(editor, "collected_sql", [])


def main():
    tag = sys.argv[1]
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results", f"django_ddl_{tag}.sql")
    with connection.cursor() as cur:
        cur.execute("SELECT VERSION()")
        (ver,) = cur.fetchone()
    _, new_sql = collect(ProjectState(), NEW_MODELS)
    _, create_sql = collect(ProjectState(), [SCOPE_CREATE])
    # AlterUniqueTogether 要按实际约束名删除旧唯一键，所以先真实建出旧表再收集迁移 SQL
    state, _ = collect(ProjectState(), [SCOPE_CREATE], execute=True)
    _, mig_sql = collect(state, SCOPE_MIGRATION)
    with connection.cursor() as cur:
        cur.execute("DROP DATABASE djddl")
    with open(out, "w") as f:
        f.write(f"-- Django {django.get_version()}, server {ver}\n")
        f.write("-- [new tables]\n" + "\n".join(new_sql) + "\n")
        f.write("-- [TimeSeriesScope create]\n" + "\n".join(create_sql) + "\n")
        f.write("-- [TimeSeriesScope migration]\n" + "\n".join(mig_sql) + "\n")
    print(open(out).read())


if __name__ == "__main__":
    main()
