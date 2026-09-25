# Agent Workflow UI v0.6.4 compatibility release

This release contains the configurable SSH rendezvous transport for Android
pairing and the cross-platform discovery qualification matrix. Consumers must
select the immutable `v0.6.4` tag and verify the commit recorded by the Agent
Workflow umbrella manifest.

## Qualification matrix

| Surface | Evidence |
| --- | --- |
| SSH discovery | Deterministic relay, VPN, DNS, public-IP, IPv4/IPv6 and redaction matrix; disposable OpenSSH round trip in CI |
| Android | Hosted `x86_64` and `arm64-v8a` unit/lint/debug APK builds; local-runner emulator workflow remains available |
| Windows | Native x64 bootstrap, GUI/TUI and discovery qualification; ARM64 job is opt-in and fails closed when unavailable |
| Rendezvous configuration | `--ssh-host`, `AWUI_SSH_HOST`, optional `--ssh-phone-host` and bind-address; `node26` is never a production default |

The initial Android registration remains bound to the explicitly configured
HTTPS endpoint. SSH is enabled only after the phone's public key is enrolled,
with host-key verification and restricted, revocable authorized-key records.

## Required checks

```sh
python3 -m pytest -q
python3 tools/run_scenarios.py
python3 tools/check_scenario_docs.py
```

Live rendezvous qualification is opt-in and must use an operator-owned SSH
alias, for example `AWUI_TEST_RENDEZVOUS_HOST=node26`. No host credentials,
private keys, or raw network diagnostics are release artifacts.
