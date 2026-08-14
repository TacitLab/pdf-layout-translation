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


def uv_tool_conflicts(uv_path: str | None) -> dict[str, object]:
    """Detect uv tools that ship clashing executables (pdf2zh 1.x vs pdf2zh-next)."""
    if not uv_path:
        return {"checked": False}
    try:
        result = subprocess.run(
            [uv_path, "tool", "list"], capture_output=True, text=True, timeout=15, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"checked": False, "error": str(exc)}
    if result.returncode != 0:
        return {"checked": False, "error": result.stderr.strip()[:300]}
    tools = [line.split()[0] for line in result.stdout.splitlines() if line and not line.startswith("-")]
    legacy = "pdf2zh" in tools
    next_gen = "pdf2zh-next" in tools
    conflict = legacy and next_gen
    return {
        "checked": True,
        "tools": tools,
        "executable_conflict": conflict,
        "detail": (
            "Both pdf2zh (1.x) and pdf2zh-next are installed and both ship a 'pdf2zh' "
            "executable; installing or upgrading either one requires --force. "
            "setup_environment.py retries with --force automatically."
            if conflict
            else None
        ),
    }


def warmup_assets() -> dict[str, object]:
    """Check the one-time BabelDOC model/font download cache (never re-downloaded)."""
    cache_dir = Path.home() / ".cache" / "babeldoc"
    models = sorted((cache_dir / "models").glob("*.onnx")) if (cache_dir / "models").is_dir() else []
    fonts_dir = cache_dir / "fonts"
    font_count = len(list(fonts_dir.glob("*.ttf"))) if fonts_dir.is_dir() else 0
    return {
        "cache_dir": str(cache_dir),
        "layout_models": [path.name for path in models],
        "font_count": font_count,
        "ready": bool(models) and font_count > 0,
        "detail": (
            "Layout model and fonts already downloaded; warmup is a one-time step, skip it."
            if models and font_count > 0
            else "Warmup assets not fully present; the first translation run will download them (large, needs network)."
        ),
    }


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
    conflicts = uv_tool_conflicts(commands["uv"]["path"] if commands["uv"]["found"] else None)
    assets = warmup_assets()
    if not engine_ready:
        verdict = "needs-engine"
        next_action = (
            "Install the engine once via scripts/setup_environment.py --apply (after user "
            "approval). Do not reinstall afterwards; the install is global and one-time."
        )
    elif not python_dependencies_ready:
        verdict = "needs-python-deps"
        next_action = (
            "Only lightweight Python packages are missing. Install exactly these, then re-run "
            "doctor once: python -m pip install PyMuPDF python-docx"
        )
    else:
        verdict = "ready"
        next_action = (
            "Environment is ready. Do NOT reinstall the engine, do NOT rerun setup, and do NOT "
            "warm up again. Proceed to preflight."
        )
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
        "uv_tools": conflicts,
        "warmup_assets": assets,
        "summary": {
            "verdict": verdict,
            "next_action": next_action,
            "engine_ready": engine_ready,
            "qa_scripts_ready": modules["pymupdf_fitz"],
            "editable_docx_ready": modules["python_docx"],
            "python_dependencies_ready": python_dependencies_ready,
            "warmup_assets_ready": assets["ready"],
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
        print(f"Verdict: {verdict}")
        print(f"Next action: {next_action}")
        print(f"Engine ready: {engine_ready}")
        print(f"Warmup assets ready: {assets['ready']}")
        print(f"PyMuPDF ready: {modules['pymupdf_fitz']}")
        print(f"python-docx ready: {modules['python_docx']}")
        for name, item in commands.items():
            print(f"{name}: {item['path'] or 'not found'}")
    return 0 if engine_ready and python_dependencies_ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
