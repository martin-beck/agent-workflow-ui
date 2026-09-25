#!/usr/bin/env bash
set -euo pipefail

usage() { echo 'Usage: tools/android-ci-local.sh [--docker|--native] [--build-only]'; }
mode=docker; build_only=0
for arg in "$@"; do
  case "$arg" in
    --docker) mode=docker;; --native) mode=native;; --build-only) build_only=1;;
    -h|--help) usage; exit 0;; *) echo "unknown option: $arg" >&2; usage >&2; exit 2;;
  esac
done
script_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
if [[ -f "$PWD/android/gradlew" ]]; then repo_root=$(pwd); else repo_root=$script_root; fi

if [[ "$mode" == docker ]]; then
  command -v docker >/dev/null || { echo 'docker is required for --docker' >&2; exit 127; }
  docker_cmd=(docker)
  if ! docker info >/dev/null 2>&1; then
    sudo -n docker info >/dev/null 2>&1 || { echo 'docker unavailable; use docker group or passwordless sudo' >&2; exit 126; }
    docker_cmd=(sudo -n docker)
  fi
  kvm_args=(); [[ -e /dev/kvm ]] && kvm_args+=(--device /dev/kvm)
  native_args=(--native); (( build_only )) && native_args+=(--build-only)
  "${docker_cmd[@]}" build --network host -f "$repo_root/android/Dockerfile.ci" -t awui-android-ci "$repo_root"
  "${docker_cmd[@]}" run --rm --network host --shm-size=2g "${kvm_args[@]}" -v "$repo_root:/workspace" -w /workspace awui-android-ci "${native_args[@]}"
  exit $?
fi
command -v java >/dev/null || { echo 'JDK 17 is required' >&2; exit 127; }
command -v adb >/dev/null || { echo 'adb is required' >&2; exit 127; }
[[ -x "$repo_root/android/gradlew" ]] || { echo 'android/gradlew is missing' >&2; exit 2; }
cd "$repo_root/android"
./gradlew --no-daemon :app:testDebugUnitTest :app:lintDebug :app:assembleDebug
(( build_only )) && exit 0
command -v emulator >/dev/null || { echo 'emulator is required' >&2; exit 127; }
adb start-server >/dev/null
emulator -list-avds | grep -qx awui-api34 || { echo 'AVD awui-api34 is missing' >&2; exit 2; }
emulator -avd awui-api34 -no-window -no-audio -no-boot-anim -no-snapshot -gpu off >/tmp/awui-emulator.log 2>&1 & emulator_pid=$!
cleanup() { kill "$emulator_pid" 2>/dev/null || true; }; trap cleanup EXIT
timeout 180s adb wait-for-device
timeout 180s bash -c 'until [[ "$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d "\r")" == 1 ]]; do sleep 2; done'
timeout 12m ./gradlew --no-daemon :app:connectedDebugAndroidTest --stacktrace
