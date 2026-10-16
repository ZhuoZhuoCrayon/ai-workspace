#!/usr/bin/env bash
# Install GitHub CLI and start github.com login when this shell can prompt.

set -euo pipefail

AUTH_HOST="github.com"

ensure_path() {
	case ":${PATH}:" in
	*":${HOME}/.local/bin:"*) ;;
	*) export PATH="${HOME}/.local/bin:${PATH}" ;;
	esac
}

install_release() {
	local os arch version asset url tmp bin
	case "$(uname -s)" in
	Linux) os="linux" ;;
	Darwin) os="macOS" ;;
	*)
		echo "gh: unsupported OS $(uname -s)" >&2
		return 1
		;;
	esac
	case "$(uname -m)" in
	x86_64 | amd64) arch="amd64" ;;
	aarch64 | arm64) arch="arm64" ;;
	*)
		echo "gh: unsupported architecture $(uname -m)" >&2
		return 1
		;;
	esac

	version="$(curl -fsSL -o /dev/null -w '%{url_effective}' https://github.com/cli/cli/releases/latest)"
	version="${version##*/v}"
	if [ "${os}" = "linux" ]; then
		asset="gh_${version}_linux_${arch}.tar.gz"
	else
		asset="gh_${version}_macOS_${arch}.zip"
	fi
	url="https://github.com/cli/cli/releases/download/v${version}/${asset}"
	tmp="$(mktemp -d)"
	curl -fsSL "${url}" -o "${tmp}/${asset}"
	if [ "${os}" = "linux" ]; then
		tar -xzf "${tmp}/${asset}" -C "${tmp}"
	else
		unzip -q "${tmp}/${asset}" -d "${tmp}"
	fi
	bin="$(find "${tmp}" -type f -path '*/bin/gh' -print -quit)"
	if [ -z "${bin}" ]; then
		echo "gh: release archive has no bin/gh" >&2
		rm -rf "${tmp}"
		return 1
	fi
	mkdir -p "${HOME}/.local/bin"
	install -m 755 "${bin}" "${HOME}/.local/bin/gh"
	rm -rf "${tmp}"
	echo "gh: installed ${version} to ${HOME}/.local/bin/gh"
}

if ! command -v gh >/dev/null 2>&1; then
	if [ "$(uname -s)" = "Darwin" ] && command -v brew >/dev/null 2>&1; then
		brew install gh
	else
		install_release
	fi
fi

ensure_path
if ! command -v gh >/dev/null 2>&1; then
	echo "gh: installed, but ${HOME}/.local/bin is not on PATH" >&2
	exit 1
fi

if gh auth status --hostname "${AUTH_HOST}" >/dev/null 2>&1; then
	echo "gh: ${AUTH_HOST} already authenticated"
	gh auth status --hostname "${AUTH_HOST}"
	exit 0
fi

echo "gh: ${AUTH_HOST} is not authenticated"
if [ -t 0 ]; then
	exec gh auth login --hostname "${AUTH_HOST}" --git-protocol https --web --skip-ssh-key
fi

cat <<EOF
gh: finish login in a terminal:
  gh auth login --hostname ${AUTH_HOST} --git-protocol https --web
EOF
