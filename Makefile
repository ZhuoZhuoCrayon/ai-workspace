SHELL := /bin/bash

NVM_DIR ?= $(HOME)/.nvm
NVM_SCRIPT ?= $(NVM_DIR)/nvm.sh
NODE_VERSION ?= 20.18.3
UV ?= uv
PRE_COMMIT ?= $(UV) run pre-commit
SKILLS_DIR ?= .agents/skills
SKILLS_MOUNT_TARGETS ?= .codebuddy .claude
SKILLS_MOUNT_BLACKLIST ?=
REGISTRY_SCRIPT ?= $(SKILLS_DIR)/project-mgr/scripts/registry.py

.PHONY: help init init-pre-commit init-skills init-gh verify verify-pre-commit verify-skills \
	skills-update skills-update-projects skills-mount repos-sync bootstrap private-pull private-push

define with_node
	if [ -f "$(NVM_SCRIPT)" ]; then \
		source "$(NVM_SCRIPT)" && nvm use $(NODE_VERSION) >/dev/null && $(1); \
	else \
		$(1); \
	fi
endef

help:
	@printf "%s\n" \
		"Available targets:" \
		"  make bootstrap           # 克隆缺失仓库，安装并挂载 skills，安装 hook" \
		"  make repos-sync          # 克隆缺失的私有仓库和注册项目" \
		"  make private-pull        # 快进拉取 private/ 的远端改动" \
		"  make private-push        # 推送 private/ 已提交的改动" \
		"  make init                # 安装 pre-commit hook 和锁文件中的 skills" \
		"  make init-pre-commit     # 安装 git pre-commit hook" \
		"  make init-skills         # 按 skills-lock.json 安装外部 skills" \
		"  make init-gh             # 安装 GitHub CLI，并在终端里登录 github.com" \
		"  make verify              # 验证 hook、断链和 skill 来源" \
		"  make skills-mount        # 将 .agents/skills 下的目录挂载到 IDE 目录" \
		"  make skills-update       # 更新工作区内的外部 skills，并链接项目 skills" \
		"Variables:" \
		"  SKILLS_DIR=$(SKILLS_DIR)       # skills 目录" \
		"  SKILLS_MOUNT_TARGETS=$(SKILLS_MOUNT_TARGETS) # 挂载目标" \
		"  SKILLS_MOUNT_BLACKLIST=$(SKILLS_MOUNT_BLACKLIST) # 跳过的 skill，空格分隔" \
		"  REGISTRY_SCRIPT=$(REGISTRY_SCRIPT) # 注册表脚本" \
		"  PROJECTS_ROOT                  # 项目存放根目录，默认 ~/Project" \
		"  UV=$(UV)                       # Python 工具入口" \
		"  PRE_COMMIT=$(PRE_COMMIT)       # pre-commit 运行入口"

init: init-pre-commit init-skills

init-pre-commit:
	@$(PRE_COMMIT) install -f
	@echo "Installed git hook: .git/hooks/pre-commit"

init-skills:
	@$(call with_node,npx skills experimental_install)
	@$(MAKE) --no-print-directory skills-update-projects
	@$(MAKE) --no-print-directory skills-mount

init-gh:
	@bash scripts/init_gh.sh

verify: verify-pre-commit verify-skills

verify-pre-commit:
	@$(PRE_COMMIT) --version
	@test -f .git/hooks/pre-commit && echo "Verified git hook: .git/hooks/pre-commit"

verify-skills:
	@python3 scripts/verify_skills.py --root "$$(pwd)"

skills-update:
	@$(call with_node,npx skills update -p -y)
	@$(MAKE) --no-print-directory skills-update-projects
	@$(MAKE) --no-print-directory skills-mount

skills-update-projects:
	@python3 scripts/sync_project_skills.py --root "$$(pwd)" \
		--skills-dir "$(SKILLS_DIR)" --registry-script "$(REGISTRY_SCRIPT)"

skills-mount:
	@set -euo pipefail; \
		workspace_root="$$(pwd)"; \
		targets=($(SKILLS_MOUNT_TARGETS)); \
		blacklist='$(strip $(SKILLS_MOUNT_BLACKLIST))'; \
		mounted_file="$$(mktemp)"; \
		trap 'rm -f "$$mounted_file"' EXIT; \
		for skill_dir in $(SKILLS_DIR)/*; do \
			[ -d "$$skill_dir" ] && [ ! -L "$$skill_dir" ] || continue; \
			skill_name="$${skill_dir##*/}"; \
			if [[ " $$blacklist " == *" $$skill_name "* ]]; then \
				echo "Ignored $$skill_name"; \
				continue; \
			fi; \
			printf "%s\n" "$$skill_name" >> "$$mounted_file"; \
			for target in "$${targets[@]}"; do \
				mkdir -p "$$target/skills"; \
				dest="$$target/skills/$$skill_name"; \
				if [ -e "$$dest" ] && [ ! -L "$$dest" ]; then \
					echo "Cannot mount skill over directory: $$dest" >&2; \
					exit 1; \
				fi; \
				ln -sfn "../../$(SKILLS_DIR)/$$skill_name" "$$dest"; \
				echo "Mounted $$skill_name -> $$dest"; \
			done; \
		done; \
		for scan_root in "$${targets[@]}"; do \
			[ -d "$$scan_root/skills" ] || continue; \
			while IFS= read -r link; do \
				name="$${link##*/}"; \
				link_target="$$(readlink "$$link")"; \
				case "$$link_target" in \
					*".agents/skills/"*) ;; \
					*) continue ;; \
				esac; \
				if ! grep -Fxq "$$name" "$$mounted_file"; then \
					rm -f "$$link"; \
					echo "Removed stale mount $$link"; \
				fi; \
			done < <(find "$$scan_root/skills" -maxdepth 1 -type l); \
		done; \
		if [ -d .cursor/skills ]; then \
			while IFS= read -r link; do \
				link_target="$$(readlink "$$link")"; \
				case "$$link_target" in \
					*".agents/skills/"*) \
						rm -f "$$link"; \
						echo "Removed retired mount $$link" ;; \
				esac; \
			done < <(find .cursor/skills -maxdepth 1 -type l); \
		fi; \
		rm -f "$$mounted_file"

repos-sync:
	@python3 "$(REGISTRY_SCRIPT)" --root "$$(pwd)" sync

private-pull:
	@git -C private pull --ff-only

private-push:
	@git -C private push

bootstrap:
	@$(MAKE) --no-print-directory repos-sync
	@$(MAKE) --no-print-directory init-skills || echo "bootstrap: init-skills failed, continuing"
	@$(MAKE) --no-print-directory skills-update-projects
	@$(MAKE) --no-print-directory skills-mount
	@$(MAKE) --no-print-directory init-pre-commit
	@$(MAKE) --no-print-directory verify
	@$(MAKE) --no-print-directory init-gh
