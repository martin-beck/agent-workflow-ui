"""Revision-bound company dashboard data exchanged with the Coordinator.

The dashboard is deliberately a small, toolkit-neutral bridge.  The
Coordinator owns the rollup; the UI only validates its identity and renders a
bounded snapshot.  A snapshot from another project or revision is rejected
before it can reach a widget.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

BOARD_SCHEMA_VERSION = "1.0"


class BoardRevisionMismatch(ValueError):
    """Raised when a dashboard snapshot is not for the active AR session."""


@dataclass(frozen=True)
class RollupPage:
    page_id: str
    title: str
    status: str
    completed: int = 0
    total: int = 0
    blocked: int = 0
    bottlenecks: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> RollupPage:
        if not isinstance(value.get("page_id"), str) or not value["page_id"]:
            raise ValueError("rollup page requires page_id")
        if not isinstance(value.get("title"), str) or not value["title"]:
            raise ValueError("rollup page requires title")
        status = value.get("status", "unknown")
        if not isinstance(status, str):
            raise TypeError("rollup page status must be text")
        numeric = {name: value.get(name, 0) for name in ("completed", "total", "blocked")}
        if any(not isinstance(number, int) or number < 0 for number in numeric.values()):
            raise ValueError("rollup page counters must be non-negative integers")
        bottlenecks = value.get("bottlenecks", ())
        if not isinstance(bottlenecks, (list, tuple)) or any(not isinstance(item, str) for item in bottlenecks):
            raise ValueError("rollup page bottlenecks must be text")
        return cls(value["page_id"], value["title"], status, **numeric, bottlenecks=tuple(bottlenecks))

    def as_dict(self) -> dict[str, Any]:
        return {"page_id": self.page_id, "title": self.title, "status": self.status,
                "completed": self.completed, "total": self.total, "blocked": self.blocked,
                "bottlenecks": list(self.bottlenecks)}


@dataclass(frozen=True)
class BoardRequest:
    project_id: str
    ar_id: str
    task_revision: int
    packet_digest: str
    rollup_revision: int
    pages: tuple[RollupPage, ...]
    schema_version: str = BOARD_SCHEMA_VERSION
    kind: str = "coordinator-board-request"

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> BoardRequest:
        if value.get("kind") != "coordinator-board-request" or value.get("schema_version") != BOARD_SCHEMA_VERSION:
            raise ValueError("unsupported Coordinator board request")
        if any(not isinstance(value.get(key), str) or not value[key] for key in ("project_id", "ar_id", "packet_digest")):
            raise ValueError("board request identity is incomplete")
        if not isinstance(value.get("task_revision"), int) or value["task_revision"] < 1:
            raise ValueError("task_revision must be positive")
        if not isinstance(value.get("rollup_revision"), int) or value["rollup_revision"] < 1:
            raise ValueError("rollup_revision must be positive")
        pages = value.get("pages")
        if not isinstance(pages, list) or not pages:
            raise ValueError("board request requires at least one rollup page")
        parsed = tuple(RollupPage.from_dict(page) for page in pages)
        if len({page.page_id for page in parsed}) != len(parsed):
            raise ValueError("rollup page ids must be unique")
        return cls(value["project_id"], value["ar_id"], value["task_revision"], value["packet_digest"], value["rollup_revision"], parsed)

    def as_dict(self) -> dict[str, Any]:
        return {"schema_version": self.schema_version, "kind": self.kind,
                "project_id": self.project_id, "ar_id": self.ar_id,
                "task_revision": self.task_revision, "packet_digest": self.packet_digest,
                "rollup_revision": self.rollup_revision, "pages": [page.as_dict() for page in self.pages]}


def render_dashboard(request: BoardRequest) -> str:
    """Render a compact, deterministic dashboard pane."""
    lines = [f"Company dashboard  |  rollup r{request.rollup_revision}",
             f"AR {request.ar_id}  revision {request.task_revision}  |  {len(request.pages)} pages", ""]
    for page in request.pages:
        progress = f"{page.completed}/{page.total}" if page.total else "-"
        blocked = f"  blocked {page.blocked}" if page.blocked else ""
        lines.append(f"{page.title}: {page.status}  progress {progress}{blocked}")
        for bottleneck in page.bottlenecks[:3]:
            lines.append(f"  ! {bottleneck}")
    return "\n".join(lines)


def accept_board_response(request: BoardRequest, response: Mapping[str, Any]) -> str:
    """Validate a board action and return its selected page id.

    The response is an observation/navigation event, never an AR mutation.
    """
    for key in ("project_id", "ar_id", "task_revision", "packet_digest", "rollup_revision"):
        if response.get(key) != getattr(request, key):
            raise BoardRevisionMismatch(f"board response {key} does not match request")
    if response.get("kind") != "coordinator-board-response" or response.get("schema_version") != BOARD_SCHEMA_VERSION:
        raise ValueError("unsupported Coordinator board response")
    page_id = response.get("page_id")
    if not isinstance(page_id, str) or page_id not in {page.page_id for page in request.pages}:
        raise ValueError("board response selects an unknown page")
    return page_id
