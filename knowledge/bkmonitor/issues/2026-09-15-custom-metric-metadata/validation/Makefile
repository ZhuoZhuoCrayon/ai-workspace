.PHONY: all env s1 s2 layout scope scope-stress catalog-smoke m1 m2 explode explode-clean meta-layout meta-layout-clean compat clean

all: env s1 s2 layout scope scope-stress

env:
	bash run.sh environment env

s1:
	bash run.sh s1_matrix matrix --scale s1

s2:
	bash run.sh s2_scale scale --scale s2

# 复用 s2 留下的表，必须紧跟 s2 执行
layout:
	bash run.sh s2_layout layout --scale s2

scope:
	bash run.sh scope_kv scope --large-services 126

scope-stress:
	bash run.sh scope_kv_stress scope --large-services 1000

# 元信息目录：100,000 指标冒烟，结论以 m1、m2 为准
catalog-smoke:
	CM_BENCH_SCRIPT=catalog.py bash run.sh catalog_smoke m1 --metrics 100000 --quick --ddl

# DDL 只与 1,000,000 行指标项表有关，只在 m1 执行
m1:
	CM_BENCH_SCRIPT=catalog.py bash run.sh m1_catalog m1 --ddl

m2:
	CM_BENCH_SCRIPT=catalog.py bash run.sh m2_catalog m2

# 展开与分表：自带 mysqld（端口 33309），完整 M1 数据目录峰值约 17 GiB
explode:
	PYTHONDONTWRITEBYTECODE=1 uv run --quiet --with 'pymysql==1.1.1' python explode.py run --out results/m1_explode.txt

explode-clean:
	PYTHONDONTWRITEBYTECODE=1 uv run --quiet --with 'pymysql==1.1.1' python explode.py clean

# 元信息不一致的存法：自带 mysqld（端口 33310），1%、10%、50% 三档依次装载并删除
meta-layout:
	PYTHONDONTWRITEBYTECODE=1 uv run --quiet --with 'pymysql==1.1.1' python meta_layout.py run --out results/meta_layout.txt

meta-layout-clean:
	PYTHONDONTWRITEBYTECODE=1 uv run --quiet --with 'pymysql==1.1.1' python meta_layout.py clean

# MySQL 5.7 与 8.0 依次在 Docker 中运行，结束即删除容器与数据卷
compat:
	bash compat/compat.sh all
	bash compat/compat.sh diff

clean:
	rm -rf "$${CM_BENCH_WORK:-$${TMPDIR:-/tmp}/cm-metric-bench}"
