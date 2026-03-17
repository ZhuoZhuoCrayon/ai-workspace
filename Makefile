SHELL := /bin/zsh

NVM_DIR ?= $(HOME)/.nvm
NODE_VERSION ?= 20.18.3
PRE_COMMIT_PYENV_VERSION ?= 3.10.4
SKILLS_SOURCE ?= https://github.com/anthropics/skills
SKILLS_IDE ?= cursor
SKILLS_DIR ?= .agents/skills
SKILLS ?= skill-creator mcp-builder docx pdf pptx xlsx webapp-testing
SKILLS_AGENT_ARGS := $(if $(strip $(SKILLS_IDE)),--agent $(SKILLS_IDE),)

.PHONY: help init init-pre-commit init-skills verify verify-pre-commit verify-skills skills-update

help:
	@printf "%s\n" \
		"Available targets:" \
		"  make init                # 初始化 pre-commit 和默认 skills" \
		"  make init-pre-commit     # 安装 git pre-commit hook" \
		"  make init-skills         # 安装默认 Anthropic skills" \
		"  make verify              # 验证 pre-commit 和 skills" \
		"  make skills-update       # 重新安装默认 skills，作为更新方式" \
		"Variables:" \
		"  SKILLS_IDE=$(SKILLS_IDE)              # 默认仅安装到 Cursor；留空则不传 --agent" \
		"  SKILLS_DIR=$(SKILLS_DIR)       # 当前默认 skills 目录" \
		"  SKILLS=$(SKILLS)"

init: init-pre-commit init-skills

init-pre-commit:
	@PYENV_VERSION=$(PRE_COMMIT_PYENV_VERSION) pre-commit install -f
	@echo "Installed git hook: .git/hooks/pre-commit"

init-skills:
	@source "$(NVM_DIR)/nvm.sh" && nvm use $(NODE_VERSION) >/dev/null && \
	for skill in $(SKILLS); do \
		echo "Installing $$skill"; \
		npx skills add $(SKILLS_SOURCE) --skill "$$skill" $(SKILLS_AGENT_ARGS) --yes; \
	done

verify: verify-pre-commit verify-skills

verify-pre-commit:
	@PYENV_VERSION=$(PRE_COMMIT_PYENV_VERSION) pre-commit --version
	@test -f .git/hooks/pre-commit && echo "Verified git hook: .git/hooks/pre-commit"

verify-skills:
	@test -d $(SKILLS_DIR)
	@ls $(SKILLS_DIR)

skills-update:
	@source "$(NVM_DIR)/nvm.sh" && nvm use $(NODE_VERSION) >/dev/null && \
	for skill in $(SKILLS); do \
		echo "Updating $$skill"; \
		npx skills add $(SKILLS_SOURCE) --skill "$$skill" $(SKILLS_AGENT_ARGS) --yes; \
	done
