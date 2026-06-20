SHELL := /bin/zsh

NVM_DIR ?= $(HOME)/.nvm
NVM_SCRIPT ?= $(NVM_DIR)/nvm.sh
NODE_VERSION ?= 20.18.3
UV ?= uv
PRE_COMMIT ?= $(UV) run pre-commit
SKILLS_SOURCE ?= https://github.com/anthropics/skills
SKILLS_IDE ?= cursor
SKILLS_DIR ?= .agents/skills
SKILLS ?= skill-creator mcp-builder docx pdf pptx xlsx webapp-testing
SKILLS_MOUNT_TARGETS ?= .codebuddy .claude .cursor
SKILLS_MOUNT_BLACKLIST ?=
SKILLS_AGENT_ARGS := $(if $(strip $(SKILLS_IDE)),--agent $(SKILLS_IDE),)

.PHONY: help init init-pre-commit init-skills verify verify-pre-commit verify-skills skills-update skills-mount

help:
	@printf "%s\n" \
		"Available targets:" \
		"  make init                # 初始化 pre-commit 和默认 skills" \
		"  make init-pre-commit     # 安装 git pre-commit hook" \
		"  make init-skills         # 安装默认 skills" \
		"  make verify              # 验证 pre-commit 和 skills" \
		"  make skills-mount        # 将 .agents/skills 下的 skills 挂载到目标目录" \
		"  make skills-update       # 重新安装默认 skills，作为更新方式" \
		"Variables:" \
		"  SKILLS_IDE=$(SKILLS_IDE)              # 默认仅安装到 Cursor；留空则不传 --agent" \
		"  SKILLS_DIR=$(SKILLS_DIR)       # 当前默认 skills 目录" \
		"  SKILLS_MOUNT_TARGETS=$(SKILLS_MOUNT_TARGETS) # 默认挂载目标目录" \
		"  SKILLS_MOUNT_BLACKLIST=$(SKILLS_MOUNT_BLACKLIST) # 可选，跳过指定 skill（空格分隔）" \
		"  UV=$(UV)                       # Python 工具统一通过 uv 运行" \
		"  PRE_COMMIT=$(PRE_COMMIT)       # pre-commit 运行入口" \
		"  SKILLS=$(SKILLS)"

init: init-pre-commit init-skills

init-pre-commit:
	@$(PRE_COMMIT) install -f
	@echo "Installed git hook: .git/hooks/pre-commit"

init-skills:
	@source "$(NVM_SCRIPT)" && nvm use $(NODE_VERSION) >/dev/null && \
		for skill in $(SKILLS); do \
			echo "Installing $$skill"; \
			npx skills add $(SKILLS_SOURCE) --skill "$$skill" $(SKILLS_AGENT_ARGS) --yes; \
		done

verify: verify-pre-commit verify-skills

verify-pre-commit:
	@$(PRE_COMMIT) --version
	@test -f .git/hooks/pre-commit && echo "Verified git hook: .git/hooks/pre-commit"

verify-skills:
	@test -d $(SKILLS_DIR)
	@ls $(SKILLS_DIR)

skills-update:
	@source "$(NVM_SCRIPT)" && nvm use $(NODE_VERSION) >/dev/null && \
		for skill in $(SKILLS); do \
			echo "Updating $$skill"; \
			npx skills add $(SKILLS_SOURCE) --skill "$$skill" $(SKILLS_AGENT_ARGS) --yes; \
		done

skills-mount:
	@set -euo pipefail; \
	workspace_root="$$(pwd)"; \
	targets=($(SKILLS_MOUNT_TARGETS)); \
	blacklist='$(strip $(SKILLS_MOUNT_BLACKLIST))'; \
	for target in "$${targets[@]}"; do \
		mkdir -p "$$target/skills"; \
		find "$$target/skills" -maxdepth 1 -type l | while read -r link; do \
			link_target="$$(readlink "$$link")"; \
			if [[ "$$link_target" == "$$workspace_root/$(SKILLS_DIR)"/* ]] && [ ! -e "$$link_target" ]; then \
				rm -f "$$link"; \
				echo "Removed stale mount $$link"; \
			fi; \
		done; \
	done; \
	for skill_dir in $(SKILLS_DIR)/*; do \
		[ -d "$$skill_dir" ] || continue; \
		skill_name="$${skill_dir##*/}"; \
		if [[ " $$blacklist " == *" $$skill_name "* ]]; then \
			continue; \
		fi; \
		src="$$workspace_root/$$skill_dir"; \
		for target in "$${targets[@]}"; do \
			dest="$$target/skills/$$skill_name"; \
			if [ -e "$$dest" ] || [ -L "$$dest" ]; then \
				rm -rf "$$dest"; \
			fi; \
			ln -s "$$src" "$$dest"; \
			echo "Mounted $$skill_name -> $$dest"; \
		done; \
	done
