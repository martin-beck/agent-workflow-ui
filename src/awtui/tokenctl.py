"""Authoritative-host token finalization helper used by remote launchers."""
from __future__ import annotations

import argparse
from pathlib import Path

from .tokens import TokenError, TokenStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="awui-token")
    sub = parser.add_subparsers(dest="action", required=True)
    consume = sub.add_parser("consume", help="atomically consume a completed batch token")
    consume.add_argument("--registry", required=True)
    consume.add_argument("--token", required=True)
    consume.add_argument("--ssh-host", required=True)
    args = parser.parse_args(argv)
    if args.action == "consume":
        try:
            TokenStore(Path(args.registry)).consume(args.token, ssh_host=args.ssh_host)
        except TokenError as exc:
            parser.error(str(exc))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
