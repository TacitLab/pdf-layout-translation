#!/usr/bin/env python3
"""Preview or apply an isolated pdf2zh-next installation."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Execute the install command")
    parser.add_argument("--python", default="3.12", help="Python version for uv tool")
    parser.add_argument("--package", default="pdf2zh-next", help="Package name")
    parser.add_argument("--force", action="store_true", help="Pass --force to uv tool install")
    args = parser.parse_args()

    existing = shutil.which("pdf2zh_next")
    if existing and not args.force:
        print(json.dumps({"status": "already-installed", "path": existing}, indent=2))
        return 0

    uv = shutil.which("uv")
    if not uv:
        print(
            "uv is not installed. Install uv using its official instructions, then rerun "
            "this script. No fallback installer was executed.",
            file=sys.stderr,
        )
        return 2

    command = [uv, "tool", "install", "--python", args.python]
    if args.force:
        command.append("--force")
    command.append(args.package)
    preview = {"status": "preview" if not args.apply else "executing", "command": command}
    print(json.dumps(preview, indent=2))
    if not args.apply:
        print("Dry run only. Re-run with --apply after the user approves installation and network access.")
        return 0
    result = subprocess.run(command, check=False)
    if result.returncode != 0:
        return result.returncode
    installed = shutil.which("pdf2zh_next")
    print(json.dumps({"status": "installed", "path": installed}, indent=2))
    return 0 if installed else 3


if __name__ == "__main__":
    raise SystemExit(main())

