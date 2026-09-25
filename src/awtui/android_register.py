"""Create a one-time Android registration QR for a workflow project."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .android_service import AndroidDeviceRegistry


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a one-time Agent Workflow Android registration QR")
    parser.add_argument("--state", required=True, help="Android service state JSON")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--endpoint", required=True, help="HTTPS Android service endpoint")
    parser.add_argument("--ttl", type=int, default=300)
    parser.add_argument("--output", type=Path, help="PNG output; omit to print the payload")
    args = parser.parse_args()
    payload = AndroidDeviceRegistry(args.state).create_bootstrap(
        project_id=args.project_id, endpoint=args.endpoint, ttl_seconds=args.ttl)
    if args.output:
        try:
            import qrcode
        except ImportError as exc:
            raise SystemExit("PNG output requires the 'android' extra: pip install agent-workflow-ui[android]") from exc
        image = qrcode.make(json.dumps(payload, separators=(",", ":")))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        image.save(args.output)
        print(args.output)
    else:
        print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()
