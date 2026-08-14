#!/usr/bin/env python3
"""Read-only environment diagnostics for PDF layout translation."""

from __future__ import annotations

import argparse
import importlib.util
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from common import SCHEMA_VERSION, utc_now


def command_version(path: str) -> dict[str, object]:
    for flag in ("--version", "-V", "--help"):
        try:
            result = subprocess.run(
                [path, flag], capture_output=True, text=True, timeout=8, check=False
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {"ok": False, "error": str(exc)}
        output = (result.stdout or result.stderr).strip().splitlines()
        if result.returncode == 0 and output:
            return {"ok": True, "returncode": 0, "summary": output[0][:300]}
    return {"ok": False, "error": "Executable did not respond successfully"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    parser.add_argument("--json-out", help="Also write the report to this path")
    args = parser.parse_args()

    commands: dict[str, object] = {}
    for name in ("pdf2zh_next", "babeldoc", "uv", "docker"):
        path = shutil.which(name)
        commands[name] = {
            "found": bool(path),
            "path": path,
            "probe": command_version(path) if path else None,
        }

    modules = {
        "pymupdf_fitz": (
            importlib.util.find_spec("pymupdf") is not None
            or importlib.util.find_spec("fitz") is not None
        ),
        "yaml": importlib.util.find_spec("yaml") is not None,
        "python_docx": importlib.util.find_spec("docx") is not None,
    }
    engine_ready = bool(
        commands["pdf2zh_next"]["found"] or commands["babeldoc"]["found"]
    )
    python_dependencies_ready = bool(modules["pymupdf_fitz"] and modules["python_docx"])
    report = {
        "schema_version": SCHEMA_VERSION,
        "tool": "doctor",
        "generated_at": utc_now(),
        "read_only": True,
        "platform": platform.platform(),
        "python": {
            "version": platform.python_version(),
            "executable": sys.executable,
            "supported": sys.version_info >= (3, 10),
        },
        "commands": commands,
        "python_modules": modules,
        "summary": {
            "engine_ready": engine_ready,
            "qa_scripts_ready": modules["pymupdf_fitz"],
            "editable_docx_ready": modules["python_docx"],
            "python_dependencies_ready": python_dependencies_ready,
            "install_needed": not engine_ready,
            "setup_required": not engine_ready or not python_dependencies_ready,
        },
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.json_out:
        output = Path(args.json_out).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
    if args.json:
        print(rendered)
    else:
        print(f"Engine ready: {engine_ready}")
        print(f"PyMuPDF ready: {modules['pymupdf_fitz']}")
        print(f"python-docx ready: {modules['python_docx']}")
        for name, item in commands.items():
            print(f"{name}: {item['path'] or 'not found'}")
    return 0 if engine_ready and python_dependencies_ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
