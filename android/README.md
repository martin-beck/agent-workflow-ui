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
