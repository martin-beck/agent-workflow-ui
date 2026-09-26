# Agent Workflow UI v0.6.6 compatibility release

This release makes SSH rendezvous metadata in the Android QR actionable for
the first connection. With `--ssh-host` and no explicit public endpoint, the
service forwards its actual TLS listener through the configured rendezvous,
derives the allocated HTTPS endpoint, and writes that endpoint into the QR.
The phone can redeem the one-time bootstrap before it has a credential or an
authorized SSH key. The rendezvous SSH server must allow a public
`GatewayPorts` bind and the certificate must be valid for the QR hostname.
