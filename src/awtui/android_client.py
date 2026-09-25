"""Small revision-bound client used by Android/network qualification tools.

The client deliberately accepts an already resolved HTTPS endpoint.  SSH
port-forwarding and host aliases remain owned by the caller's SSH config; this
keeps credentials out of shell command construction while allowing localhost,
LAN and forwarded endpoints to use the same contract.
"""
from __future__ import annotations

import json
import ssl
import time
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class AndroidRemoteClient:
    endpoint: str
    device_id: str
    credential: str
    timeout: float = 5.0
    verify_tls: bool = True

    def _call(self, method: str, path: str, payload: dict | None = None) -> dict:
        body = None if payload is None else json.dumps(payload, sort_keys=True).encode()
        headers = {"Accept": "application/json", "Authorization": f"Bearer {self.credential}",
                   "X-Device-Id": self.device_id, "Content-Type": "application/json"}
        request = Request(self.endpoint.rstrip("/") + path, data=body, headers=headers, method=method)
        context = None if self.verify_tls else ssl._create_unverified_context()
        try:
            with urlopen(request, timeout=self.timeout, context=context) as response:
                return json.loads(response.read())
        except (HTTPError, URLError, TimeoutError) as exc:
            raise ConnectionError(f"Android service request failed: {method} {path}") from exc

    def poll(self) -> dict:
        return self._call("GET", "/v1/session")

    def submit(self, *, message: dict, project_id: str, session_id: str,
               task_revision: int, packet_digest: str) -> dict:
        return self._call("POST", "/v1/events", {
            "device_id": self.device_id, "project_id": project_id,
            "session_id": session_id, "task_revision": task_revision,
            "packet_digest": packet_digest, "message": message,
        })

    def poll_until_available(self, *, attempts: int = 5, delay: float = 0.2) -> dict:
        if attempts < 1:
            raise ValueError("attempts must be positive")
        last: dict = {"status": "idle", "batch": None}
        for index in range(attempts):
            last = self.poll()
            if last.get("batch") is not None:
                return last
            if index + 1 < attempts:
                time.sleep(delay)
        return last
