"""Authoritative-host token finalization helper used by remote launchers."""
from __future__ import annotations

import argparse
from pathlib import Path

import json

from .tokens import TokenError, TokenStore, issue_for_batch


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="awui-token")
    sub = parser.add_subparsers(dest="action", required=True)
    issue = sub.add_parser("issue", help="issue one token for a complete batch request")
    issue.add_argument("--registry", required=True)
    issue.add_argument("--request", required=True)
    issue.add_argument("--session-file", required=True)
    issue.add_argument("--event-file", required=True)
    issue.add_argument("--ssh-host", required=True)
    issue.add_argument("--ttl", type=int, default=900)
    consume = sub.add_parser("consume", help="atomically consume a completed batch token")
    consume.add_argument("--registry", required=True)
    consume.add_argument("--token", required=True)
    consume.add_argument("--ssh-host", required=True)
    args = parser.parse_args(argv)
    if args.action == "issue":
        try:
            request = json.loads(Path(args.request).read_text(encoding="utf-8"))
            print(issue_for_batch(args.registry, request,
                                  session_file=args.session_file,
                                  event_file=args.event_file,
                                  ssh_host=args.ssh_host,
                                  ttl_seconds=args.ttl))
        except (OSError, ValueError, TokenError) as exc:
            parser.error(str(exc))
        return 0
    if args.action == "consume":
        try:
            TokenStore(Path(args.registry)).consume(args.token, ssh_host=args.ssh_host)
        except TokenError as exc:
            parser.error(str(exc))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
