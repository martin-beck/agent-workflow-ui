"""Deterministic P-256 OpenSSH test identities; never used by product code."""
import base64
import hashlib
import struct

from awtui.android import enrollment_proof_message

P = 0xffffffff00000001000000000000000000000000ffffffffffffffffffffffff
N = 0xffffffff00000000ffffffffffffffffbce6faada7179e84f3b9cac2fc632551
A = P - 3
G = (0x6b17d1f2e12c4247f8bce6e563a440f277037d812deb33a0f4a13945d898c296,
     0x4fe342e2fe1a7f9b8ee7eb4a7c0f9e162bce33576b315ececbb6406837bf51f5)


def _add(left, right):
    if left is None:
        return right
    if right is None:
        return left
    x1, y1 = left
    x2, y2 = right
    if x1 == x2 and (y1 + y2) % P == 0:
        return None
    slope = ((3 * x1 * x1 + A) * pow(2 * y1, -1, P) if left == right
             else (y2 - y1) * pow((x2 - x1) % P, -1, P)) % P
    x3 = (slope * slope - x1 - x2) % P
    return x3, (slope * (x1 - x3) - y1) % P


def _mul(scalar, point):
    result = None
    while scalar:
        if scalar & 1:
            result = _add(result, point)
        point = _add(point, point)
        scalar >>= 1
    return result


def _ssh_string(value):
    return struct.pack(">I", len(value)) + value


def _der_int(value):
    raw = value.to_bytes((value.bit_length() + 7) // 8, "big") or b"\0"
    if raw[0] & 0x80:
        raw = b"\0" + raw
    return b"\x02" + bytes([len(raw)]) + raw


def sign_registration(qr, private_scalar=12345):
    public = _mul(private_scalar, G)
    point = b"\x04" + public[0].to_bytes(32, "big") + public[1].to_bytes(32, "big")
    blob = _ssh_string(b"ecdsa-sha2-nistp256") + _ssh_string(b"nistp256") + _ssh_string(point)
    public_key = "ecdsa-sha2-nistp256 " + base64.b64encode(blob).decode() + " test-device"
    digest = int.from_bytes(hashlib.sha256(enrollment_proof_message(qr)).digest(), "big")
    nonce = 987654321
    r = _mul(nonce, G)[0] % N
    s = (pow(nonce, -1, N) * (digest + r * private_scalar)) % N
    body = _der_int(r) + _der_int(s)
    der = b"\x30" + bytes([len(body)]) + body
    signature = base64.b64encode(der).decode()
    return public_key, signature
