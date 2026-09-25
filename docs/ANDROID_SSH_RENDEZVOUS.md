# Android SSH rendezvous

The Android SSH transport is optional and configured on the workflow service.
The service uses its existing OpenSSH configuration to connect to a selected
rendezvous host, such as `node26`, and opens a restricted reverse forward to a
loopback-only Android service listener.

```text
awui-android-service --state .runtime/android-service.json \
  --host 127.0.0.1 --port 8765 \
  --certfile service.crt --keyfile service.key \
  --ssh-host node26 \
  --ssh-phone-host 217.110.131.81
```

`--ssh-host` is configurable and may be any safe OpenSSH alias from the
service account's SSH configuration. `--ssh-phone-host` overrides the address
advertised to the phone when split DNS or an SSH alias is service-local. The
temporary `node26` qualification profile is opt-in and must not be hard-coded
into production configuration.

The service validates the configured host key from `known_hosts`, installs only
an explicitly approved, restricted public key, and never transfers a private
key. The QR contains the rendezvous candidate, host-key fingerprint, forward
port, expiry, and project binding. It does not contain a private key.

Initial registration still requires the HTTPS `--endpoint` passed to
`awui-android-register` to be reachable from the phone. The SSH tunnel is
established after the one-time registration installs the phone public key; this
prevents an unauthenticated bootstrap port from being exposed. If the service
HTTPS endpoint is not reachable, an independently configured HTTPS reverse
proxy/VPN/relay is required for the initial enrollment.

The opt-in live qualification uses the existing SSH alias without committing
credentials:

```text
AWUI_TEST_RENDEZVOUS_HOST=node26 \
  python -m pytest -q tests/test_android_ssh.py -k configured_rendezvous
```
