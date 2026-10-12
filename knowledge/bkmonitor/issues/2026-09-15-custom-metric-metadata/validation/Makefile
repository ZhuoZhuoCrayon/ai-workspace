.PHONY: all env s1 s2 layout scope scope-stress catalog-smoke m1 m2 explode explode-clean meta-layout meta-layout-clean compat plans57 plans57-arm64 plans57-supplement plans57-supplement2 plans57-clean clean

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

# 四个完整方案在 MySQL 5.7 上对比：自带 Docker 容器（端口 33311），数据目录峰值约 9 GiB，结束即删除容器与数据卷
plans57:
	PYTHONDONTWRITEBYTECODE=1 uv run --quiet --with 'pymysql==1.1.1' python plans57.py run --out results/plans57.txt

# 原生 arm64 的 5.7 社区构建复测 A/C/D 的读取与全平台扫描，排除 amd64 模拟的影响
plans57-arm64:
	IMAGE_57=biarms/mysql:5.7 PLATFORM_57=linux/arm64 PYTHONDONTWRITEBYTECODE=1 uv run --quiet --with 'pymysql==1.1.1' \
		python plans57.py run --cross-check --out results/plans57_arm64.txt

# 补测管理页搜索、族视图节点分页与单范围读取，只装载指标项、定义与最大数据源的成员，再在 arm64 原生构建上复核排序
plans57-supplement:
	PYTHONDONTWRITEBYTECODE=1 uv run --quiet --with 'pymysql==1.1.1' \
		python plans57.py run --supplement --out results/plans57_supplement.txt
	IMAGE_57=biarms/mysql:5.7 PLATFORM_57=linux/arm64 PYTHONDONTWRITEBYTECODE=1 uv run --quiet --with 'pymysql==1.1.1' \
		python plans57.py run --supplement --cross-check --out results/plans57_supplement_arm64.txt

# 补测 C 按 PLAN 写法（C2）、族视图首页完整步骤与服务视图完整路径，再在 arm64 原生构建上复核排序
plans57-supplement2:
	PYTHONDONTWRITEBYTECODE=1 uv run --quiet --with 'pymysql==1.1.1' \
		python plans57.py run --supplement2 --out results/plans57_supplement2.txt
	IMAGE_57=biarms/mysql:5.7 PLATFORM_57=linux/arm64 PYTHONDONTWRITEBYTECODE=1 uv run --quiet --with 'pymysql==1.1.1' \
		python plans57.py run --supplement2 --cross-check --out results/plans57_supplement2_arm64.txt

plans57-clean:
	PYTHONDONTWRITEBYTECODE=1 uv run --quiet --with 'pymysql==1.1.1' python plans57.py clean

clean:
	rm -rf "$${CM_BENCH_WORK:-$${TMPDIR:-/tmp}/cm-metric-bench}"
