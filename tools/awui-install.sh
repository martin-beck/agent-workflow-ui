#!/bin/sh
# Install or repair the per-user Agent Workflow UI launcher on POSIX systems.
# No administrator privileges are required.  This script intentionally writes
# only below the user's home directory.
set -eu

action=Install
ssh_host=
remote_root=
release=v0.6.0
install_root=${AWUI_INSTALL_ROOT:-${XDG_DATA_HOME:-${HOME:?}/.local/share}/agent-workflow-ui}
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

usage() {
    cat >&2 <<'EOF'
usage: awui-install.sh [--action install|repair|uninstall|version]
       [--ssh-host ALIAS] [--remote-state-root PATH] [--release vX.Y.Z]
       [--install-root PATH] [--force]
EOF
    exit 2
}
while [ "$#" -gt 0 ]; do
    case $1 in
        --action) [ "$#" -ge 2 ] || usage; action=$2; shift 2 ;;
        --ssh-host) [ "$#" -ge 2 ] || usage; ssh_host=$2; shift 2 ;;
        --remote-state-root) [ "$#" -ge 2 ] || usage; remote_root=$2; shift 2 ;;
        --release) [ "$#" -ge 2 ] || usage; release=$2; shift 2 ;;
        --install-root) [ "$#" -ge 2 ] || usage; install_root=$2; shift 2 ;;
        --force) force=1; shift ;;
        -h|--help) usage ;;
        *) usage ;;
    esac
done
force=${force:-0}
case $action in
    install|Install) action=Install ;; repair|Repair) action=Repair ;;
    uninstall|Uninstall) action=Uninstall ;; version|Version) action=Version ;;
    *) usage ;;
esac
printf '%s\n' "$release" | grep -Eq '^v[0-9]+\.[0-9]+\.[0-9]+$' || { echo 'invalid release tag' >&2; exit 2; }
case $install_root in /*) ;; *) echo 'install root must be absolute' >&2; exit 2 ;; esac
case $install_root in *[!A-Za-z0-9._/@+:-]*) echo 'install root contains unsafe characters' >&2; exit 2 ;; esac
case $install_root in /|/bin|/etc|/home|/root|/usr|/var|/tmp) echo 'install root is too broad' >&2; exit 2 ;; esac

bin=$install_root/bin
runtime=$install_root/runtime
config=$install_root/config.json
launcher=$bin/awui
installer=$bin/awui-install.sh
launcher_url=https://raw.githubusercontent.com/martin-beck/agent-workflow-ui/$release/tools/awui
installer_url=https://raw.githubusercontent.com/martin-beck/agent-workflow-ui/$release/tools/awui-install.sh

fetch() {
    url=$1; destination=$2
    if command -v curl >/dev/null 2>&1; then curl -fsSL -- "$url" -o "$destination"
    elif command -v wget >/dev/null 2>&1; then wget -qO "$destination" -- "$url"
    else echo 'awui installer requires curl or wget' >&2; exit 1; fi
}
sha256() {
    if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | awk '{print $1}'
    elif command -v shasum >/dev/null 2>&1; then shasum -a 256 "$1" | awk '{print $1}'
    else echo 'awui installer requires sha256sum or shasum' >&2; exit 1; fi
}
safe_alias() { [ -z "$1" ] || printf '%s' "$1" | grep -Eq '^[A-Za-z0-9][A-Za-z0-9_.-]{0,62}$'; }
safe_root() { [ -z "$1" ] || { case $1 in /*) ;; *) return 1 ;; esac; case $1 in *..*|*[!A-Za-z0-9._/@+:-]*) return 1 ;; esac; }; }

if [ "$action" = Version ]; then
    if [ -f "$config" ]; then cat "$config"; else echo 'awui is not installed.'; fi
    exit 0
fi
if [ "$action" = Uninstall ]; then
    rm -rf -- "$install_root"
    echo 'awui removed from this user profile.'
    exit 0
fi
[ "$action" = Install ] && [ -e "$install_root" ] && [ "$force" -ne 1 ] && {
    echo 'awui is already installed; use --action repair or --force.' >&2; exit 1;
}
safe_alias "$ssh_host" || { echo 'SSH host must be an SSH config alias.' >&2; exit 2; }
safe_root "$remote_root" || { echo 'remote state root must be an absolute safe path.' >&2; exit 2; }
python_bin=${PYTHON_BIN:-python3}
command -v "$python_bin" >/dev/null 2>&1 || { echo 'Python 3.11+ is required.' >&2; exit 1; }
"$python_bin" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' || { echo 'Python 3.11+ is required.' >&2; exit 1; }

umask 077
mkdir -p -- "$bin"
tmp=$(mktemp "${TMPDIR:-/tmp}/awui-install.XXXXXX")
trap 'rm -f "$tmp"' EXIT HUP INT TERM
if [ -f "$script_dir/awui" ]; then cp -- "$script_dir/awui" "$tmp"; else fetch "$launcher_url" "$tmp"; fi
# This hash is deliberately pinned to the launcher in this release.  Refuse
# to install a changed or substituted launcher.
expected_sha256=9cb77d80b305196028b08219f2c7241351a61d2290dc132d53e4722ddba8dde9
[ "$(sha256 "$tmp")" = "$expected_sha256" ] || { echo 'launcher hash validation failed; refusing installation.' >&2; exit 1; }
install -m 700 -- "$tmp" "$launcher"
if [ -f "$script_dir/awui-install.sh" ]; then cp -- "$script_dir/awui-install.sh" "$installer"; else fetch "$installer_url" "$installer"; chmod 700 "$installer"; fi
if [ ! -x "$runtime/bin/python" ]; then "$python_bin" -m venv "$runtime"; fi
"$runtime/bin/python" -m pip install --disable-pip-version-check --quiet --upgrade "agent-workflow-ui[gui] @ https://github.com/martin-beck/agent-workflow-ui/archive/refs/tags/$release.zip"
old_host= old_root=
if [ -f "$config" ]; then old_host=$(sed -n 's/.*"ssh_host"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$config" | head -n 1); old_root=$(sed -n 's/.*"remote_state_root"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$config" | head -n 1); fi
printf '{\n  "schema_version": "1",\n  "ssh_host": "%s",\n  "remote_state_root": "%s",\n  "release": "%s",\n  "runtime_root": "%s",\n  "launcher_version": "1"\n}\n' "${ssh_host:-$old_host}" "${remote_root:-$old_root}" "$release" "$runtime" > "$config"
mkdir -p -- "${HOME:?}/.local/bin"
if [ ! -e "${HOME:?}/.local/bin/awui" ] || [ "$install_root/bin/awui" != "${HOME:?}/.local/bin/awui" ]; then
    ln -sfn -- "$launcher" "${HOME:?}/.local/bin/awui"
fi
echo "awui installed in $install_root (ensure ~/.local/bin is on PATH)."
