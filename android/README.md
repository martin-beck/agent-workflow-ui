# Agent Workflow UI Android development build

This is an unsigned development APK, not a store release. Build it with:

```text
./gradlew :app:assembleDebug
```

The APK is written to `app/build/outputs/apk/debug/app-debug.apk`. Install it
with `adb install -r` or `android install --apks ...` on a development device.

Open **Register phone**, allow camera access, and scan the QR displayed by the
project-side `awui-android-service`. The app shows the project and HTTPS
endpoint before consent, generates its device key in Android Keystore, and
redeems the one-time bootstrap. After registration, decision batches use the
same project/session/revision/packet-digest bindings as the TUI and GUI.

The current client includes the complete batch workspace interaction surface:
decision list and progress, Design/Work plan Markdown panes, active context,
proposal selection, own-proposal editing, Save, and registration/reconnect
status. Network delivery is fail-closed on stale, replayed, revoked, or
cross-device events.

## Qualification and CI evidence

The Android workflow runs JVM tests, lint, and an unsigned debug APK build for
the x86_64 and arm64-v8a compatibility lanes. The APK is a universal debug
APK; the ABI lanes ensure the Kotlin/Compose dependency graph remains usable
on both emulator and arm64 device classes. Each lane publishes the APK,
SHA-256 checksum, Gradle/Java metadata, and the resolved runtime dependency
report. No signing key or production credential is used.

The hosted emulator lane uses an API 35 `google_apis` Pixel 2 x86_64 image,
disables animations, runs the instrumented batch-selection, Save, and
document-tab tests, and uploads the Android test reports and a diagnostic
screenshot even when a test fails. The lane has a hard timeout so a broken
emulator cannot leave a pull request indefinitely pending.

The Python adapter qualification (`tests/test_android_server.py`) exercises
the same registration, service-authenticated batch publication, session
polling, and revision-bound event route used by the emulator client. A real
device smoke test remains intentionally manual: install the unsigned APK,
scan a project QR code, approve registration, select a batch proposal, and
verify the service journal before and after briefly disabling the network.
