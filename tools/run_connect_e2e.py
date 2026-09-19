#!/usr/bin/env python3
"""Exercise connector request/result transfer with a deterministic UI shim."""
from __future__ import annotations

import argparse
import json
import os
import stat
import tempfile
from pathlib import Path

from awtui.connect import connect


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ssh-host", required=True)
    parser.add_argument("--remote-request", required=True)
    parser.add_argument("--remote-result", required=True)
    parser.add_argument("--backend", choices=("gui", "tui"), required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="awui-connect-e2e-") as root:
        shim = Path(root) / ("awui-live" if args.backend == "gui" else "awtui-live")
        shim.write_text(
            "#!/usr/bin/env python3\n"
            "import json, pathlib, sys\n"
            "args=sys.argv\n"
            "request=pathlib.Path(args[args.index('--session-file')+1])\n"
            "output=pathlib.Path(args[args.index('--output-json')+1])\n"
            "data=json.loads(request.read_text())\n"
            "event={'project_id':data['project_id'],'ar_id':data['ar']['ar_id'],"
            "'task_revision':data['ar']['task_revision'],'packet_digest':'sha256:'+'a'*64,"
            "'session_id':data['session_id'],'sequence':1,'event_type':'select',"
            "'payload':{'point_id':'AWG-CONNECT-E2E','disposition':'select',"
            "'selected':'candidate-a','selected_candidate':'candidate-a'}}\n"
            "output.write_text(json.dumps(event)+'\\n')\n"
        )
        shim.chmod(shim.stat().st_mode | stat.S_IXUSR)
        old_path = os.environ.get("PATH", "")
        os.environ["PATH"] = f"{root}{os.pathsep}{old_path}"
        try:
            code = connect(session_file=args.remote_request, ssh_host=args.ssh_host,
                           remote_event_file=args.remote_result, backend=args.backend)
        finally:
            os.environ["PATH"] = old_path
    return code


if __name__ == "__main__":
    raise SystemExit(main())
