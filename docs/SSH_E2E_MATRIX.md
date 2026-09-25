# SSH discovery and tunnel qualification matrix

The repository tests the rendezvous path without requiring a public SSH host.
`tests/test_ssh_e2e_matrix.py` runs the same redacted discovery contract for
Linux, Windows, and Android profiles and covers relay, VPN, DNS, and explicit
public-IP candidates, including IPv4 and IPv6 resolution. The normal scenario
workflow also starts a disposable OpenSSH daemon and exercises the complete
revision-bound round trip.

The Android build workflow compiles and tests both `x86_64` and `arm64-v8a`.
The Windows workflow runs on native x64, with an opt-in native ARM64 runner;
the local Android runner workflow provides emulator qualification when a
development machine has an Android SDK and emulator configured.

For an operator-selected live qualification, set the configured OpenSSH alias
without putting it into source or CI defaults:

```sh
AWUI_TEST_RENDEZVOUS_HOST=node26 \
  python -m pytest -q tests/test_endpoint_discovery.py -k opt_in_configured
```

The `node26` profile is only a temporary test fixture. Production deployments
must pass their own `--ssh-host`/`AWUI_SSH_HOST` alias and must independently
verify reachability and host keys.
