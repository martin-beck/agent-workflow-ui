#!/usr/bin/env bash
set -Eeuo pipefail

# Local Android qualification runner. It is safe to invoke from a self-hosted
# Actions runner or directly from a developer checkout. It never registers a
# GitHub runner and never stores credentials.
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
android_home=${ANDROID_SDK_ROOT:-${ANDROID_HOME:-"${AWUI_ANDROID_HOME:-$HOME/.local/share/awui-android-sdk}"}}
avd_name=${AWUI_ANDROID_AVD:-awui-api34}
api_level=${AWUI_ANDROID_API_LEVEL:-34}
system_image=${AWUI_ANDROID_SYSTEM_IMAGE:-"system-images;android-${api_level};google_apis;x86_64"}

die() { echo "awui-android-runner: $*" >&2; exit 2; }
log() { echo "awui-android-runner: $*" >&2; }
have() { command -v "$1" >/dev/null 2>&1; }

sdk_bin() {
  local name=$1
  if [[ -x "$android_home/cmdline-tools/latest/bin/$name" ]]; then
    printf '%s\n' "$android_home/cmdline-tools/latest/bin/$name"
  elif have "$name"; then
    command -v "$name"
  else
    die "$name is not installed; run '$0 bootstrap' first"
  fi
}

doctor() {
  local failed=0
  [[ "$(uname -s)" == Linux ]] || { log "self-hosted Android runner currently supports Linux only"; failed=1; }
  have java || { log "missing java (JDK 17 is required)"; failed=1; }
  have curl || { log "missing curl"; failed=1; }
  have unzip || { log "missing unzip"; failed=1; }
  [[ -d "$android_home" ]] || { log "missing Android SDK: $android_home"; failed=1; }
  [[ -x "$android_home/platform-tools/adb" ]] || { log "missing Android SDK platform-tools"; failed=1; }
  [[ -x "$android_home/emulator/emulator" ]] || { log "missing Android emulator"; failed=1; }
  [[ -e /dev/kvm ]] || log "warning: /dev/kvm is unavailable; emulator will be very slow"
  [[ $failed -eq 0 ]] || return 1
  java -version 2>&1 | head -1
  "$android_home/platform-tools/adb" version | head -1
  "$android_home/emulator/emulator" -version 2>&1 | head -1
  log "Android runner prerequisites are available"
}

install_host_packages() {
  if have apt-get; then
    sudo apt-get update
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
      ca-certificates curl unzip openjdk-17-jdk qemu-kvm libvirt-daemon-system \
      libvirt-clients bridge-utils cpu-checker
  elif have dnf; then
    sudo dnf install -y ca-certificates curl unzip java-17-openjdk-devel @virtualization
  elif have pacman; then
    sudo pacman -Sy --needed --noconfirm ca-certificates curl unzip jdk17-openjdk qemu-desktop libvirt
  else
    die "unsupported package manager; install JDK 17, curl, unzip, and KVM packages manually"
  fi
}

install_sdk() {
  mkdir -p "$android_home"
  local sdkmanager="$android_home/cmdline-tools/latest/bin/sdkmanager"
  if [[ ! -x "$sdkmanager" ]]; then
    local version=${AWUI_CMDLINE_TOOLS_VERSION:-13114758}
    local archive="$android_home/commandlinetools-linux-${version}_latest.zip"
    local url="https://dl.google.com/android/repository/commandlinetools-linux-${version}_latest.zip"
    log "downloading pinned Android command-line tools ${version}"
    curl --fail --location --retry 3 --output "$archive" "$url"
    local unpack
    unpack=$(mktemp -d)
    unzip -q "$archive" -d "$unpack"
    rm -rf "$android_home/cmdline-tools/latest"
    mkdir -p "$android_home/cmdline-tools/latest"
    cp -a "$unpack/cmdline-tools/." "$android_home/cmdline-tools/latest/"
    rm -rf "$unpack" "$archive"
  fi
  yes | "$sdkmanager" --sdk_root="$android_home" --licenses >/dev/null || true
  yes | "$sdkmanager" --sdk_root="$android_home" \
    "platform-tools" "emulator" "platforms;android-36" "build-tools;36.0.0" "$system_image"
}

ensure_avd() {
  local avdmanager
  avdmanager=$(sdk_bin avdmanager)
  if ! "$avdmanager" list avd | grep -q "Name: ${avd_name}$"; then
    printf 'no\n' | "$avdmanager" create avd --force --name "$avd_name" \
      --package "$system_image" --device pixel_2
  fi
}

bootstrap() {
  install_host_packages
  install_sdk
  ensure_avd
  doctor
  log "runner bootstrap complete; SDK=$android_home AVD=$avd_name"
}

e2e() {
  doctor
  ensure_avd
  local adb="$android_home/platform-tools/adb"
  local emulator="$android_home/emulator/emulator"
  local serial="emulator-5554"
  local log_file=${AWUI_ANDROID_EMULATOR_LOG:-"$repo_root/android/build/local-emulator.log"}
  mkdir -p "$(dirname "$log_file")"
  "$adb" start-server >/dev/null
  if "$adb" devices | awk 'NR > 1 {print $1}' | grep -qx "$serial"; then
    "$adb" -s "$serial" emu kill >/dev/null 2>&1 || true
    sleep 2
  fi
  log "starting $avd_name on $serial"
  "$emulator" -avd "$avd_name" -port 5554 -no-window -no-audio \
    -no-boot-anim -no-snapshot -gpu swiftshader_indirect >"$log_file" 2>&1 &
  local emulator_pid=$!
  cleanup() {
    "$adb" -s "$serial" emu kill >/dev/null 2>&1 || true
    kill "$emulator_pid" >/dev/null 2>&1 || true
    wait "$emulator_pid" >/dev/null 2>&1 || true
  }
  trap cleanup EXIT
  "$adb" -s "$serial" wait-for-device
  local deadline=$((SECONDS + ${AWUI_ANDROID_BOOT_TIMEOUT:-180}))
  until [[ "$("$adb" -s "$serial" shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" == 1 ]]; do
    (( SECONDS < deadline )) || { tail -100 "$log_file" >&2; die "emulator did not boot before timeout"; }
    sleep 2
  done
  "$adb" -s "$serial" shell settings put global window_animation_scale 0
  "$adb" -s "$serial" shell settings put global transition_animation_scale 0
  "$adb" -s "$serial" shell settings put global animator_duration_scale 0
  (cd "$repo_root/android" && timeout "${AWUI_ANDROID_TEST_TIMEOUT:-12m}" \
    ./gradlew --no-daemon :app:connectedDebugAndroidTest --stacktrace)
  mkdir -p "$repo_root/android/build/connected-artifacts"
  "$adb" -s "$serial" exec-out screencap -p > \
    "$repo_root/android/build/connected-artifacts/emulator-workspace.png"
  log "local Android emulator E2E passed"
}

usage() {
  cat >&2 <<EOF
Usage: $0 {bootstrap|doctor|e2e}

  bootstrap  install host packages, Android SDK packages, and the pinned AVD
  doctor     verify local runner prerequisites without changing anything
  e2e        start the AVD, run connectedDebugAndroidTest, and capture a screenshot

Environment overrides: ANDROID_SDK_ROOT, AWUI_ANDROID_HOME, AWUI_ANDROID_AVD,
AWUI_ANDROID_API_LEVEL, AWUI_ANDROID_BOOT_TIMEOUT, AWUI_ANDROID_TEST_TIMEOUT.
EOF
}

case "${1:-}" in
  bootstrap) bootstrap ;;
  doctor) doctor ;;
  e2e) e2e ;;
  *) usage; exit 2 ;;
esac
