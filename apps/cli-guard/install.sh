#!/bin/sh
# Install a verified engine and a PATH wrapper; preserve user shell configuration.
set -eu
export LC_ALL=C

root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
data_home=${XDG_DATA_HOME:-$HOME/.local/share}
directory=$data_home/cli_guard
begin='# >>> cli-guard >>>'
end='# <<< cli-guard <<<'
python=${PYTHON:-python3}
real_gh=
config=
dry_run=false
remove=false

fail() { printf 'cli-guard: %s\n' "$*" >&2; exit 1; }
quote() { printf "'%s'" "$(printf '%s' "$1" | sed "s/'/'\\\\''/g")"; }
managed() { head -c 96 "$1" | grep -q '^# cli-guard managed$'; }

while [ "$#" -gt 0 ]; do
    case "$1" in
        --dry-run) dry_run=true ;;
        --remove) remove=true ;;
        --real-gh) [ "$#" -ge 2 ] || fail '--real-gh requires a path.'; real_gh=$2; shift ;;
        --config) [ "$#" -ge 2 ] && [ -n "$2" ] || fail '--config requires a path.'; config=$2; shift ;;
        *) fail 'Usage: sh install.sh [--config PATH] [--dry-run] [--remove] [--real-gh PATH]' ;;
    esac
    shift
done

work=$(mktemp -d)
stage=
trap 'rm -rf "$work"; [ -z "$stage" ] || rm -f "$stage"' 0
trap 'exit 1' HUP INT TERM

# Read content from stdin; replace atomically only when the bytes differ.
write_file() {
    destination=$1
    mode=$2
    cat > "$work/content"
    if cmp -s "$work/content" "$destination"; then
        if [ "$mode" = 755 ] && ! "$dry_run"; then chmod 755 "$destination"; fi
        return
    fi
    if "$dry_run"; then printf 'Would write: %s\n' "$destination"; return; fi
    if [ -L "$destination" ]; then
        destination=$("$python" -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$destination")
    fi
    mkdir -p "$(dirname "$destination")"
    stage=$(mktemp "$destination.XXXXXX")
    case "$mode" in
        preserve) if [ -f "$destination" ]; then cp -p "$destination" "$stage"; else chmod 644 "$stage"; fi ;;
        *) chmod "$mode" "$stage" ;;
    esac
    cat "$work/content" > "$stage"
    mv -f "$stage" "$destination"
    stage=
    printf 'Writing: %s\n' "$destination"
}

find_original() {
    search_path=$PATH
    while :; do
        entry=${search_path%%:*}
        candidate=${entry:-.}/$1
        if [ -f "$candidate" ] && [ -x "$candidate" ] && \
            ! managed "$candidate"; then
            printf '%s\n' "$candidate"
            return
        fi
        [ "$search_path" != "$entry" ] || break
        search_path=${search_path#*:}
    done
}

if ! "$remove"; then
    "$python" -c 'import sys; sys.exit(sys.version_info < (3,11))' 2>/dev/null || fail 'Python 3.11+ is required. Set PYTHON to its executable path.'
    python=$("$python" -c 'import sys; print(sys.executable)')
    set -- "$python" -B "$root/guard.py"
    if [ -n "$config" ]; then
        config=$("$python" -c 'import os,sys; print(os.path.abspath(sys.argv[1]))' "$config")
        set -- "$@" --config "$config"
    fi
    tools=$("$@" --list-tools) || fail 'Invalid configuration. Installation stopped.'
    : > "$work/commands"
    for tool in $tools; do
        original=$(find_original "$tool")
        if [ "$tool" = gh ] && [ -n "$real_gh" ]; then original=$real_gh; fi
        if [ -z "$original" ]; then
            printf 'Skipping %s: original command not found.\n' "$tool"
            continue
        fi
        [ -f "$original" ] && [ -x "$original" ] || fail "Original $tool is not executable."
        if managed "$original"; then
            fail "Original $tool resolves to another guard."
        fi
        case "$original" in
            /*) ;;
            *) original=$(CDPATH= cd -- "$(dirname -- "$original")" && pwd)/$(basename -- "$original") ;;
        esac
        launcher=$directory/bin/$tool
        if [ -e "$launcher" ] && ! managed "$launcher"; then
            fail "The installation path contains an unmanaged $tool. Installation stopped."
        fi
        printf '%s\t%s\n' "$tool" "$original" >> "$work/commands"
    done
    [ -s "$work/commands" ] || fail 'No supported CLI found on PATH.'
    dispatcher=$directory/bin/cli-guard
    if [ -e "$dispatcher" ] && ! managed "$dispatcher"; then
        fail 'The installation path contains an unmanaged cli-guard. Installation stopped.'
    fi

    case "$(uname -s)" in Darwin) system=darwin ;; Linux) system=linux ;; *) fail 'Only Linux and macOS are supported.' ;; esac
    case "$(uname -m)" in arm64|aarch64) arch=arm64 ;; x86_64|amd64) arch=x64 ;; *) fail 'Only arm64 and x64 are supported.' ;; esac
    read -r version < "$root/betterleaks.lock"
    hashes=$(awk -v target="${system}_${arch}" '$1 == target {print $2, $3}' "$root/betterleaks.lock")
    [ -n "$hashes" ] || fail 'Platform checksums are missing from betterleaks.lock.'
    archive_hash=${hashes%% *}
    binary_hash=${hashes#* }
    if command -v sha256sum >/dev/null 2>&1; then
        sha256() { sha256sum "$1" | cut -d ' ' -f 1; }
    else
        command -v shasum >/dev/null 2>&1 || fail 'sha256sum or shasum is required.'
        sha256() { shasum -a 256 "$1" | cut -d ' ' -f 1; }
    fi
    engine=$directory/engine/$version/betterleaks
    if [ -f "$engine" ] && [ "$(sha256 "$engine")" = "$binary_hash" ]; then
        if ! "$dry_run"; then chmod 755 "$engine"; fi
    elif "$dry_run"; then
        printf 'Would install: Betterleaks %s (%s_%s).\n' "$version" "$system" "$arch"
    else
        printf 'Installing: Betterleaks %s (%s_%s).\n' "$version" "$system" "$arch"
        command -v curl >/dev/null 2>&1 || fail 'curl is required for the first installation.'
        curl -fsSL --retry 2 --connect-timeout 15 --max-time 120 -o "$work/release.tar.gz" "https://github.com/betterleaks/betterleaks/releases/download/v$version/betterleaks_${version}_${system}_${arch}.tar.gz" || fail 'Betterleaks download failed. Retry the installation.'
        [ "$(sha256 "$work/release.tar.gz")" = "$archive_hash" ] || fail 'Betterleaks archive checksum mismatch.'
        tar -xOf "$work/release.tar.gz" betterleaks > "$work/betterleaks"
        [ "$(sha256 "$work/betterleaks")" = "$binary_hash" ] || fail 'Betterleaks executable checksum mismatch.'
        write_file "$engine" 755 < "$work/betterleaks"
    fi
    {
        printf '#!/bin/sh\n# cli-guard managed\nexec %s -B %s' "$(quote "$python")" "$(quote "$root/guard.py")"
        if [ -n "$config" ]; then printf ' --config %s' "$(quote "$config")"; fi
        printf ' "$@"\n'
    } > "$work/launcher"
    write_file "$dispatcher" 755 < "$work/launcher"
    while IFS="$(printf '\t')" read -r tool original; do
        printf '#!/bin/sh\n# cli-guard managed\nexec %s %s %s "$@"\n' \
            "$(quote "$dispatcher")" \
            "$(quote "$tool")" "$(quote "$original")" > "$work/launcher"
        write_file "$directory/bin/$tool" 755 < "$work/launcher"
    done < "$work/commands"
    printf 'case "$PATH" in\n  %s:*) ;;\n  *) export PATH=%s:"$PATH" ;;\nesac\n' "$(quote "$directory/bin")" "$(quote "$directory/bin")" > "$work/env"
    write_file "$directory/env.sh" 644 < "$work/env"
fi

# Reassert PATH after system/login/interactive setup; preserve Bash login precedence.
for name in .zshenv .zprofile .zshrc .profile .bash_profile .bash_login .bashrc; do
    file=$HOME/$name
    [ -f "$file" ] || [ -L "$file" ] || { "$remove" && continue; case "$name" in .zshenv|.zprofile|.zshrc|.profile|.bashrc) ;; *) continue ;; esac; }
    if [ -f "$file" ]; then
        awk -v begin="$begin" -v end="$end" '
            $0 == begin {if (skip) exit 1; skip=1; next}
            $0 == end {skip=0; next}
            !skip {print}
            END {if (skip) exit 1}
        ' "$file" > "$work/profile" || fail "Unclosed managed block in $name. Repair it and retry."
    else
        : > "$work/profile"
    fi
    if ! "$remove"; then
        printf '%s\n[ ! -f %s ] || . %s\n%s\n' "$begin" "$(quote "$directory/env.sh")" "$(quote "$directory/env.sh")" "$end" >> "$work/profile"
    fi
    write_file "$file" preserve < "$work/profile"
done

if "$remove"; then
    for launcher in "$directory"/bin/*; do
        if [ -f "$launcher" ] && managed "$launcher"; then
            if "$dry_run"; then printf 'Would remove: %s\n' "$launcher";
            else rm -f "$launcher"; fi
        fi
    done
    if ! "$dry_run"; then rm -f "$directory/env.sh"; fi
    printf 'cli-guard: Removed. New terminals use the original commands. The verified engine cache is retained.\n'
else
    printf 'cli-guard: Ready. New terminals load the guard automatically. For this terminal, run: . %s\n' "$(quote "$directory/env.sh")"
fi
