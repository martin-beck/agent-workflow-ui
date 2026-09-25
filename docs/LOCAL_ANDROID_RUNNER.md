# Local Android CI runner

The Android emulator qualification can run on a private Linux machine instead
of a hosted runner. The checked-in runner script installs the JDK, Android SDK
command-line tools, emulator, API 34 Google APIs x86_64 image, and a named AVD.
It also checks KVM availability and bounds both emulator boot and Gradle test
execution.

## One-time machine setup

From a clean checkout, run:

```sh
tools/awui-android-runner.sh bootstrap
```

The default SDK location is `$HOME/.local/share/awui-android-sdk`. Set
`AWUI_ANDROID_HOME` or `ANDROID_SDK_ROOT` to use another location. `bootstrap`
uses the host package manager (`apt`, `dnf`, or `pacman`) and may ask for sudo.
It does not add a user to groups or change unrelated virtualization settings;
the account running the emulator must already be allowed to access `/dev/kvm`.

Verify without changing the machine:

```sh
tools/awui-android-runner.sh doctor
```

## Local qualification

Run the same emulator qualification used by the local Actions workflow:

```sh
tools/awui-android-runner.sh e2e
```

The command starts only the named `awui-api34` AVD, runs
`connectedDebugAndroidTest`, saves the emulator log and captures
`android/build/connected-artifacts/emulator-workspace.png`. It shuts down that
AVD on success, failure, or interruption. Override
`AWUI_ANDROID_BOOT_TIMEOUT` and `AWUI_ANDROID_TEST_TIMEOUT` only when a slower
machine needs a longer bounded timeout.

## Optional GitHub Actions self-hosted runner

Create a repository-scoped runner in GitHub Settings → Actions → Runners and
follow GitHub's displayed, short-lived registration command on the private
machine. Choose the labels `self-hosted`, `linux`, `x64`, and `android`, and
run the runner as a dedicated unprivileged account. Do not commit or paste the
registration token into this repository. Start the runner as a service only
after `tools/awui-android-runner.sh doctor` passes.

The manual `Android local-runner qualification` workflow targets exactly those
labels. It is deliberately `workflow_dispatch`-only, so untrusted pull
requests cannot execute arbitrary code on a private machine. The hosted build
and emulator workflow remains available for public pull requests; the local
workflow is the controlled qualification path when hosted emulator capacity is
unreliable.

The self-hosted runner must have outbound HTTPS access to GitHub, Maven, and
Google's Android repository, and must retain enough disk for Gradle and the
API 34 system image. Runner registration credentials are managed by GitHub and
are not handled by the AWUI script.
