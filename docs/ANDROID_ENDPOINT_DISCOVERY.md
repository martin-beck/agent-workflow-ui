# Android SSH endpoint discovery

`awui-endpoints` resolves an OpenSSH alias with `ssh -G`, enumerates A/AAAA
addresses, reads the configured port, and collects SSH public host-key
fingerprints with `ssh-keyscan`. Its output uses
[`android-endpoint-candidates.schema.json`](../schemas/android-endpoint-candidates.schema.json).
It contains no SSH username, key path, proxy command, credentials, or raw
OpenSSH output. A `ssh-keyscan` fingerprint is an observation only; the phone
must compare the SSH handshake key with an independently approved fingerprint.

Configure the rendezvous alias with `--ssh-host` or
`AWUI_RENDEZVOUS_HOST`. An alternate config file is selected with
`--ssh-config` or `AWUI_SSH_CONFIG`. The alias is evaluated on the service
machine, so its private/split-DNS names are only candidates; the Android phone
must perform the authoritative probe from its own network.

Optional candidates can be supplied explicitly, for example:

```sh
awui-endpoints --ssh-host node26 \
  --candidate vpn=workflow.vpn.example \
  --candidate relay=relay.example.net \
  --candidate public_ip=198.51.100.24
```

An HTTPS public-IP reflection provider is contacted only when explicitly set
with `--reflection-url` or `AWUI_PUBLIC_IP_REFLECTION_URL`. The response is
bounded and must be one globally routable IP address. No provider, STUN server,
VPN, relay, or Internet connection is required for offline/local operation.
Relay and VPN candidates sort ahead of configured DNS/name candidates, which
sort ahead of raw public-IP candidates. Expiry and provenance travel with each
candidate. The discovery layer does not claim that NAT/firewall rules allow
inbound access.

For offline fixture coverage of the user-local `node26` SSH alias, tests create
a temporary, credential-free config containing that alias and a documentation
address. CI never reads developer SSH files and never contacts the real host.
An external TCP reachability smoke test is opt-in only:

```sh
AWUI_TEST_RENDEZVOUS_HOST=node26 pytest -q tests/test_endpoint_discovery.py -k opt_in
```

The Android `EndpointCandidateProbe` orders candidates, enforces expiry and
fingerprint presence, and returns a result with a stable failure code for each
candidate. Its TCP check is only reachability evidence; SSH authentication and
host-key verification are performed by the tunnel handshake implementation.
