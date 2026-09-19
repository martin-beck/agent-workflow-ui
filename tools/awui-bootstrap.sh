#!/usr/bin/env sh
# Small POSIX bootstrap fetched from the authoritative SSH host.  It installs
# the pinned release into the invoking Python environment and uses the module
# entry point so a newly-created console-script directory need not be on PATH.
set -eu
: "${AWUI_SSH_HOST:?set AWUI_SSH_HOST}"
: "${AWUI_SESSION_FILE:?set AWUI_SESSION_FILE}"
: "${AWUI_REMOTE_EVENT_FILE:?set AWUI_REMOTE_EVENT_FILE}"
AWUI_BACKEND="${AWUI_BACKEND:-}"
AWUI_RELEASE="${AWUI_RELEASE:-v0.4.12}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
ARCHITECTURE="$(uname -m 2>/dev/null || printf unknown)"
KERNEL="$(uname -s 2>/dev/null || printf unknown)"
DISTRO="unknown"
[ -r /etc/os-release ] && . /etc/os-release && DISTRO="${PRETTY_NAME:-$ID}"
PYTHON_VERSION="$($PYTHON_BIN --version 2>&1 || true)"
printf '%s\n' "Agent Workflow UI bootstrap: platform=$KERNEL architecture=$ARCHITECTURE distro=$DISTRO runtime=$PYTHON_VERSION" >&2
if [ "${AWUI_PROBE_ONLY:-0}" = 1 ]; then exit 0; fi
if [ -z "$AWUI_BACKEND" ]; then
  if [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]; then AWUI_BACKEND=gui; else AWUI_BACKEND=tui; fi
fi
RUNTIME_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/awui-runtime.XXXXXX")"
trap 'rm -rf "$RUNTIME_ROOT"' EXIT HUP INT TERM
"$PYTHON_BIN" -m venv "$RUNTIME_ROOT/venv"
VENV_PYTHON="$RUNTIME_ROOT/venv/bin/python"
if ! "$VENV_PYTHON" -m pip install --quiet "agent-workflow-ui[gui] @ https://github.com/martin-beck/agent-workflow-ui/archive/refs/tags/${AWUI_RELEASE}.zip"; then
  AWUI_BACKEND=tui
  "$VENV_PYTHON" -m pip install --quiet "agent-workflow-ui @ https://github.com/martin-beck/agent-workflow-ui/archive/refs/tags/${AWUI_RELEASE}.zip"
fi
exec "$VENV_PYTHON" -m awtui.connect \
  --ssh-host "$AWUI_SSH_HOST" \
  --session-file "$AWUI_SESSION_FILE" \
  --remote-event-file "$AWUI_REMOTE_EVENT_FILE" \
  --backend "$AWUI_BACKEND"
