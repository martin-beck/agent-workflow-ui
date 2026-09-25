"""Privacy-preserving SSH endpoint candidate discovery for Android pairing.

Discovery is advisory: only a probe from the phone's network can establish
reachability. SSH config is evaluated by OpenSSH and never copied to output.
"""
from __future__ import annotations

import base64
import argparse
import hashlib
import ipaddress
import json
import os
import socket
import subprocess
import urllib.parse
import urllib.request
import urllib.error
from dataclasses import asdict, dataclass
from typing import Callable, Iterable


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    source_alias: str
    host: str
    port: int
    address_family: str
    provenance: str
    priority: int
    host_key_fingerprints: tuple[str, ...]
    expires_at: int | None = None


@dataclass(frozen=True)
class DiscoveryResult:
    schema_version: int
    candidates: tuple[Candidate, ...]
    diagnostics: tuple[str, ...]

    def public_dict(self) -> dict:
        return {"schema_version": self.schema_version,
                "candidates": [asdict(item) for item in self.candidates],
                "diagnostics": list(self.diagnostics)}


def _parse_ssh_config(output: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in output.splitlines():
        parts = line.split(None, 1)
        if len(parts) == 2:
            values.setdefault(parts[0].lower(), parts[1].strip())
    return values


def _addresses(host: str) -> list[tuple[str, str]]:
    try:
        records = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except (OSError, UnicodeError):
        return []
    found: dict[str, str] = {}
    for family, _, _, _, sockaddr in records:
        address = sockaddr[0].split("%", 1)[0]
        try:
            parsed = ipaddress.ip_address(address)
        except ValueError:
            continue
        found[address] = "ipv6" if family == socket.AF_INET6 else "ipv4"
        if parsed.is_unspecified or parsed.is_multicast:
            found.pop(address, None)
    return sorted(found.items(), key=lambda item: (item[1], item[0]))


def _fingerprints(host: str, port: int, *, run: Callable = subprocess.run) -> tuple[str, ...]:
    try:
        result = run(["ssh-keyscan", "-T", "3", "-p", str(port), host],
                     capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return ()
    fingerprints = set()
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) < 3 or fields[0].startswith("#"):
            continue
        try:
            key = base64.b64decode(fields[2], validate=True)
        except (ValueError, TypeError):
            continue
        digest = base64.b64encode(hashlib.sha256(key).digest()).decode().rstrip("=")
        fingerprints.add("SHA256:" + digest)
    return tuple(sorted(fingerprints))


def discover_ssh_candidates(alias: str | None = None, *, config_path: str | None = None,
                            rendezvous_host: str | None = None, run: Callable = subprocess.run,
                            resolver: Callable = _addresses,
                            optional_candidates: Iterable[dict] = ()) -> DiscoveryResult:
    """Enumerate safe candidates. Optional candidates are caller-verified hints.

    ``optional_candidates`` accepts explicit ``dns``, ``vpn``, ``relay`` or
    ``public_ip`` records; no external discovery service is contacted here.
    """
    alias = rendezvous_host or alias or os.environ.get("AWUI_RENDEZVOUS_HOST", "")
    if not alias or any(ch.isspace() for ch in alias) or alias.startswith("-"):
        raise ValueError("SSH alias must be one non-option token")
    diagnostics: list[str] = []
    try:
        argv = ["ssh", "-G"]
        if config_path:
            argv.extend(["-F", config_path])
        argv.extend(["--", alias])
        config = run(argv, capture_output=True, text=True,
                     timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return DiscoveryResult(1, (), ("ssh_config_unavailable",))
    if config.returncode:
        return DiscoveryResult(1, (), ("ssh_alias_unresolved",))
    values = _parse_ssh_config(config.stdout)
    host = values.get("hostname", alias)
    try:
        port = int(values.get("port", "22"))
        if not 1 <= port <= 65535:
            raise ValueError
    except ValueError:
        return DiscoveryResult(1, (), ("ssh_port_invalid",))
    hosts: list[tuple[str, str, int]] = [(host, "ssh_config", 20)]
    for address, family in resolver(host):
        try:
            parsed = ipaddress.ip_address(address)
        except ValueError:
            continue
        if parsed.is_loopback or parsed.is_link_local or parsed.is_unspecified or parsed.is_multicast:
            diagnostics.append("non_phone_routable_address_omitted")
            continue
        hosts.append((address, "vpn" if parsed.is_private else "dns_address", 30 if parsed.is_private else 40))
    candidates: list[Candidate] = []
    seen = set()
    inputs = [(host, source, priority, None) for host, source, priority in hosts]
    inputs.extend((str(x.get("host", "")), str(x.get("provenance", "")),
                   int(x.get("priority", 50)), x.get("expires_at")) for x in optional_candidates)
    for candidate_host, source, priority, expires_at in inputs:
        try:
            addr = ipaddress.ip_address(candidate_host)
        except ValueError:
            addr = None
        if not candidate_host or any(c.isspace() for c in candidate_host) or candidate_host.startswith("-"):
            diagnostics.append("invalid_candidate_omitted")
            continue
        if addr and (addr.is_loopback or addr.is_link_local or addr.is_unspecified or addr.is_multicast):
            diagnostics.append("non_phone_routable_address_omitted")
            continue
        if source not in {"ssh_config", "vpn", "dns_address", "dns", "relay", "public_ip"}:
            diagnostics.append("unknown_candidate_provenance_omitted")
            continue
        if source == "relay": priority = 10
        elif source == "vpn": priority = 20
        elif source in {"ssh_config", "dns"}: priority = 30
        elif source == "public_ip": priority = 80
        family = "ipv6" if addr and addr.version == 6 else "ipv4" if addr else "name"
        key = (candidate_host, port)
        if key in seen: continue
        seen.add(key)
        fps = _fingerprints(candidate_host, port, run=run)
        if not fps:
            diagnostics.append("host_key_unavailable_for_candidate")
        if expires_at is not None and (not isinstance(expires_at, int) or expires_at <= 0):
            diagnostics.append("invalid_candidate_expiry_omitted")
            expires_at = None
        candidates.append(Candidate("ssh-" + hashlib.sha256(f"{candidate_host}:{port}".encode()).hexdigest()[:16],
                                    alias, candidate_host, port, family, source, priority, fps, expires_at))
    candidates.sort(key=lambda c: (c.priority, c.host, c.port))
    if not candidates:
        diagnostics.append("no_phone_candidate_discovered")
    # Only stable codes are exposed: never surface ssh output, usernames, paths or env.
    return DiscoveryResult(1, tuple(candidates), tuple(dict.fromkeys(diagnostics)))


def dumps_public(result: DiscoveryResult) -> str:
    return json.dumps(result.public_dict(), sort_keys=True, separators=(",", ":"))


def reflected_public_ip(url: str, *, fetch: Callable = urllib.request.urlopen) -> dict:
    """Ask an explicitly configured HTTPS reflection provider for this host's IP.

    The provider is never contacted unless its URL is explicitly configured.
    Response text is treated as untrusted input and limited to 128 bytes.
    """
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("reflection provider must be an HTTPS URL without embedded credentials")
    try:
        with fetch(url, timeout=3) as response:
            raw = response.read(129)
    except Exception as exc:
        raise ValueError("public_ip_reflection_unavailable") from exc
    if len(raw) > 128:
        raise ValueError("public_ip_reflection_invalid")
    value = raw.decode("ascii", errors="ignore").strip()
    try:
        address = ipaddress.ip_address(value)
    except ValueError as exc:
        raise ValueError("public_ip_reflection_invalid") from exc
    if not address.is_global:
        raise ValueError("public_ip_reflection_not_public")
    return {"host": str(address), "provenance": "public_ip", "expires_at": None}


def main() -> None:
    parser = argparse.ArgumentParser(description="Enumerate phone-side SSH endpoint candidates")
    parser.add_argument("--ssh-host", default=os.environ.get("AWUI_RENDEZVOUS_HOST"),
                        help="OpenSSH alias (or AWUI_RENDEZVOUS_HOST)")
    parser.add_argument("--ssh-config", default=os.environ.get("AWUI_SSH_CONFIG"),
                        help="optional OpenSSH config file (or AWUI_SSH_CONFIG)")
    parser.add_argument("--candidate", action="append", default=[], metavar="SOURCE=HOST",
                        help="explicit dns, vpn, relay, or public_ip candidate; may be repeated")
    parser.add_argument("--reflection-url", default=os.environ.get("AWUI_PUBLIC_IP_REFLECTION_URL"),
                        help="optional HTTPS IP-reflection service; or AWUI_PUBLIC_IP_REFLECTION_URL")
    args = parser.parse_args()
    hints = []
    for item in args.candidate:
        source, sep, host = item.partition("=")
        if not sep:
            parser.error("--candidate must be SOURCE=HOST")
        hints.append({"provenance": source, "host": host})
    if args.reflection_url:
        try:
            hints.append(reflected_public_ip(args.reflection_url))
        except ValueError as exc:
            # Emit a stable diagnostic, never the URL or provider response.
            print(json.dumps({"schema_version": 1, "candidates": [],
                              "diagnostics": [str(exc)]}, sort_keys=True))
            return
    result = discover_ssh_candidates(args.ssh_host, config_path=args.ssh_config,
                                     optional_candidates=hints)
    print(dumps_public(result))


if __name__ == "__main__":
    main()
