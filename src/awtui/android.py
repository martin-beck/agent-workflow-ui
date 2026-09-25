"""Protocol-neutral Android registration and decision bridge helpers.

The phone is another renderer, not an authority.  These helpers deliberately
keep QR bootstrap payloads capability-free: the one-time bootstrap id and
nonce are redeemed by the project service before a device credential exists.
"""
from __future__ import annotations

import re
import base64
import hashlib
import json
import struct
from typing import Any

ANDROID_BRIDGE_VERSION = "1.0"
_DIGEST = re.compile(r"^sha256:[0-9a-fA-F]{64}$")
_SSH_TYPES = {"ecdsa-sha2-nistp256", "ssh-ed25519", "ssh-rsa"}


def _ssh_string(value: bytes) -> bytes:
    return struct.pack(">I", len(value)) + value


def _read_ssh_string(value: bytes, offset: int) -> tuple[bytes, int]:
    if offset + 4 > len(value):
        raise ValueError("truncated SSH public key")
    length = struct.unpack(">I", value[offset:offset + 4])[0]
    start = offset + 4
    end = start + length
    if end > len(value):
        raise ValueError("truncated SSH public key")
    return value[start:end], end


def ssh_public_key_fingerprint(public_key: str) -> str:
    """Return the OpenSSH SHA256 fingerprint for a validated public key."""
    try:
        key_type, encoded, *_ = public_key.strip().split()
        blob = base64.b64decode(encoded, validate=True)
        embedded_type, _ = _read_ssh_string(blob, 0)
    except (ValueError, TypeError) as exc:
        raise ValueError("invalid OpenSSH public key") from exc
    if key_type not in _SSH_TYPES or embedded_type.decode("ascii", "strict") != key_type:
        raise ValueError("unsupported or mismatched OpenSSH public key type")
    return "SHA256:" + base64.b64encode(hashlib.sha256(blob).digest()).decode().rstrip("=")


def enrollment_proof_message(qr: dict[str, Any]) -> bytes:
    """Canonical user-consented proof input; mirrored in Android DeviceIdentity."""
    rendezvous = qr.get("ssh_rendezvous") or {}
    values = [str(qr.get(name, "")) for name in ("project_id", "bootstrap_id", "nonce", "expires_at")]
    values.append(str(rendezvous.get("host_key_fingerprint", "")))
    if any("\n" in value or "\r" in value for value in values):
        raise ValueError("registration proof fields cannot contain line breaks")
    return ("awui-android-enrollment-v1\n" + "\n".join(values)).encode("utf-8")


def verify_ecdsa_signature(public_key: str, message: bytes, signature: str) -> None:
    """Verify an ECDSA P-256 signature with stdlib-only arithmetic.

    The wire format is a normal OpenSSH ecdsa-sha2-nistp256 authorized_keys
    public key. Private key material is never accepted by this function.
    """
    try:
        key_type, encoded, *_ = public_key.strip().split()
        blob = base64.b64decode(encoded, validate=True)
        embedded_type, offset = _read_ssh_string(blob, 0)
        curve, offset = _read_ssh_string(blob, offset)
        point, offset = _read_ssh_string(blob, offset)
        if offset != len(blob) or key_type != "ecdsa-sha2-nistp256" or embedded_type != key_type.encode() or curve != b"nistp256":
            raise ValueError
        if len(point) != 65 or point[0] != 4:
            raise ValueError
        qx, qy = int.from_bytes(point[1:33], "big"), int.from_bytes(point[33:65], "big")
        signature_der = base64.b64decode(signature, validate=True)
        # Strict DER sequence of two positive INTEGER values.
        if len(signature_der) < 8 or signature_der[0] != 0x30 or signature_der[1] != len(signature_der) - 2:
            raise ValueError
        cursor = 2
        values = []
        for _ in range(2):
            if signature_der[cursor] != 0x02:
                raise ValueError
            length = signature_der[cursor + 1]
            item = signature_der[cursor + 2:cursor + 2 + length]
            if not item or item[0] & 0x80 or (len(item) > 1 and item[0] == 0 and item[1] < 0x80):
                raise ValueError
            values.append(int.from_bytes(item, "big"))
            cursor += 2 + length
        if cursor != len(signature_der):
            raise ValueError
        r, s = values
    except (ValueError, IndexError, UnicodeError, struct.error) as exc:
        raise ValueError("invalid Android SSH proof key or signature") from exc

    # NIST P-256 domain parameters and ECDSA verification.
    p = 0xffffffff00000001000000000000000000000000ffffffffffffffffffffffff
    n = 0xffffffff00000000ffffffffffffffffbce6faada7179e84f3b9cac2fc632551
    a = p - 3
    b = 0x5ac635d8aa3a93e7b3ebbd55769886bc651d06b0cc53b0f63bce3c3e27d2604b
    gx = 0x6b17d1f2e12c4247f8bce6e563a440f277037d812deb33a0f4a13945d898c296
    gy = 0x4fe342e2fe1a7f9b8ee7eb4a7c0f9e162bce33576b315ececbb6406837bf51f5

    def add(left: tuple[int, int] | None, right: tuple[int, int] | None) -> tuple[int, int] | None:
        if left is None:
            return right
        if right is None:
            return left
        x1, y1 = left
        x2, y2 = right
        if x1 == x2 and (y1 + y2) % p == 0:
            return None
        slope = ((3 * x1 * x1 + a) * pow(2 * y1, -1, p) if left == right
                 else (y2 - y1) * pow((x2 - x1) % p, -1, p)) % p
        x3 = (slope * slope - x1 - x2) % p
        return x3, (slope * (x1 - x3) - y1) % p

    def multiply(scalar: int, point: tuple[int, int]) -> tuple[int, int] | None:
        result, addend = None, point
        while scalar:
            if scalar & 1:
                result = add(result, addend)
            addend = add(addend, addend)
            scalar >>= 1
        return result

    if not (0 < r < n and 0 < s < n and 0 <= qx < p and 0 <= qy < p):
        raise ValueError("invalid Android SSH enrollment signature")
    if (qy * qy - (qx * qx * qx + a * qx + b)) % p:
        raise ValueError("Android SSH enrollment key is not on P-256")
    digest = int.from_bytes(hashlib.sha256(message).digest(), "big")
    inverse = pow(s, -1, n)
    candidate = add(multiply((digest * inverse) % n, (gx, gy)),
                    multiply((r * inverse) % n, (qx, qy)))
    if candidate is None or candidate[0] % n != r:
        raise ValueError("Android SSH proof verification failed")


def verify_enrollment_proof(qr: dict[str, Any], public_key: str, signature: str) -> None:
    """Verify QR possession proof; private material never leaves the Android Keystore."""
    verify_ecdsa_signature(public_key, enrollment_proof_message(qr), signature)


def registration_qr(*, project_id: str, endpoint: str, bootstrap_id: str,
                    expires_at: str, nonce: str,
                    ssh_rendezvous: dict[str, Any] | None = None) -> dict[str, Any]:
    if not project_id or not endpoint.startswith("https://"):
        raise ValueError("registration requires project id and HTTPS endpoint")
    if not re.fullmatch(r"[A-Za-z0-9_-]{16,128}", bootstrap_id):
        raise ValueError("bootstrap id has invalid shape")
    if not re.fullmatch(r"[A-Fa-f0-9]{32,128}", nonce):
        raise ValueError("registration nonce has invalid shape")
    payload = {"schema_version": ANDROID_BRIDGE_VERSION,
            "kind": "android-registration-qr", "project_id": project_id,
            "bootstrap_id": bootstrap_id, "endpoint": endpoint,
            "expires_at": expires_at, "nonce": nonce}
    if ssh_rendezvous is not None:
        required = {"host", "port", "username", "forward_port", "host_key_fingerprint"}
        if set(ssh_rendezvous) != required:
            raise ValueError("SSH rendezvous metadata must contain exactly host, port, username, forward_port, and host_key_fingerprint")
        host = ssh_rendezvous["host"]
        username = ssh_rendezvous["username"]
        port = ssh_rendezvous["port"]
        forward_port = ssh_rendezvous["forward_port"]
        fingerprint = ssh_rendezvous["host_key_fingerprint"]
        if (not isinstance(host, str) or not host or len(host) > 253 or any(ch.isspace() for ch in host)
                or not isinstance(username, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", username)
                or not isinstance(port, int) or not 1 <= port <= 65535
                or not isinstance(forward_port, int) or not 1 <= forward_port <= 65535
                or not isinstance(fingerprint, str) or not re.fullmatch(r"SHA256:[A-Za-z0-9+/]{43}", fingerprint)):
            raise ValueError("invalid SSH rendezvous metadata")
        # The first registration request still uses the explicitly configured
        # HTTPS endpoint.  The SSH tunnel becomes usable only after this
        # request installs the phone public key through the approved service
        # enrollment callback; synthesizing an unauthenticated HTTP endpoint
        # on the rendezvous host would create a bootstrap bypass.
        payload["ssh_rendezvous"] = dict(ssh_rendezvous)
    return payload


def registration_request(qr: dict[str, Any], *, device_public_key: str,
                         capabilities: list[str], proof_signature: str,
                         consent: bool) -> dict[str, Any]:
    if qr.get("kind") != "android-registration-qr":
        raise ValueError("not an Android registration QR payload")
    if consent is not True:
        raise ValueError("explicit user consent is required for Android registration")
    if not device_public_key or len(device_public_key) < 32:
        raise ValueError("device public key is required")
    if not proof_signature:
        raise ValueError("Android Keystore proof of possession is required")
    allowed = {"schema_version", "kind", "project_id", "bootstrap_id", "endpoint", "expires_at", "nonce", "ssh_rendezvous", "bootstrap_endpoint"}
    if set(qr) - allowed:
        raise ValueError("registration QR contains unsupported or secret-bearing fields")
    rendezvous = qr.get("ssh_rendezvous")
    if rendezvous:
        host = rendezvous.get("host", "")
        display_host = f"[{host}]" if ":" in host and not host.startswith("[") else host
        expected_bootstrap = f"http://{display_host}:{rendezvous.get('forward_port')}"
        if qr.get("bootstrap_endpoint") != expected_bootstrap:
            raise ValueError("registration bootstrap endpoint does not match the SSH rendezvous candidate")
    elif "bootstrap_endpoint" in qr:
        raise ValueError("direct HTTPS registration cannot include a tunnel bootstrap endpoint")
    verify_enrollment_proof(qr, device_public_key, proof_signature)
    request = {**qr, "kind": "android-registration-request",
            "device_public_key": device_public_key,
            "capabilities": sorted(set(capabilities)),
            "proof_signature": proof_signature, "consent": True}
    return request


def validate_decision_message(message: dict[str, Any], *, project_id: str,
                              session_id: str, task_revision: int,
                              packet_digest: str, device_id: str | None = None) -> None:
    """Fail closed unless a phone message is bound to the active revision."""
    required = ("schema_version", "kind", "project_id", "session_id",
                "task_revision", "packet_digest", "sequence")
    if any(key not in message for key in required):
        raise ValueError("Android message is missing a required binding")
    if message["schema_version"] != ANDROID_BRIDGE_VERSION:
        raise ValueError("unsupported Android bridge version")
    if message["kind"] not in {"android-decision-request", "android-decision-event", "android-ack"}:
        raise ValueError("invalid Android bridge message kind")
    if message["project_id"] != project_id or message["session_id"] != session_id:
        raise ValueError("Android message crosses project or session boundary")
    if message["task_revision"] != task_revision or message["packet_digest"] != packet_digest:
        raise ValueError("stale Android decision message")
    if not isinstance(message["sequence"], int) or message["sequence"] < 1:
        raise ValueError("Android message sequence must be positive")
    if device_id is not None and message.get("device_id") != device_id:
        raise ValueError("Android message comes from an unexpected device")
    if not _DIGEST.fullmatch(message["packet_digest"]):
        raise ValueError("invalid packet digest")
