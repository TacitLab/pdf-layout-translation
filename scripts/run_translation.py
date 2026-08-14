#!/usr/bin/env python3
"""Build, record, and optionally execute a version-aware PDF translation command."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Iterable

from common import SCHEMA_VERSION, require_file, sha256_file, utc_now, write_json

SECRET_OPTION_RE = re.compile(r"(?:api[-_]?key|secret|password|token)", re.I)
AGENT_BRIDGE_OPTIONS = (
    "--translations-jsonl",
    "--translation-map",
    "--pretranslated-jsonl",
    "--custom-translator",
    "--translator-callback",
)


def supported(help_text: str, options: Iterable[str]) -> str | None:
    for option in options:
        if re.search(rf"(?<![\w-]){re.escape(option)}(?![\w-])", help_text):
            return option
    return None


def add_option(command: list[str], help_text: str, names: tuple[str, ...], value: str | None, label: str) -> None:
    if value is None:
        return
    option = supported(help_text, names)
    if not option:
        raise SystemExit(f"Installed engine does not expose a supported {label} option: {names}")
    command.extend([option, value])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--source-lang", required=True)
    parser.add_argument("--target-lang", required=True)
    parser.add_argument("--glossary")
    parser.add_argument("--profile-prompt")
    parser.add_argument("--pages", help="Engine page selection syntax, normally 1-based")
    parser.add_argument("--max-pages-per-part", type=int)
    parser.add_argument("--ocr", action="store_true")
    parser.add_argument("--ignore-cache", action="store_true")
    parser.add_argument("--engine", help="Explicit pdf2zh_next or babeldoc executable")
    parser.add_argument("--run-record", required=True)
    parser.add_argument(
        "--translation-backend",
        choices=("google", "current-agent", "configured"),
        default="google",
        help="User-facing translation choice; PDF engineering remains automatic",
    )
    parser.add_argument(
        "--configured-service",
        help="Service flag name for configured mode, for example deepl or ollama",
    )
    parser.add_argument(
        "--agent-translations",
        help="Validated JSONL produced by the current Agent for reinjection",
    )
    parser.add_argument(
        "--context-mode",
        choices=("global-profile", "native-engine", "current-agent"),
        default="global-profile",
    )
    parser.add_argument("--execute", action="store_true")
    args, passthrough = parser.parse_known_args()

    pdf = require_file(args.pdf, "PDF")
    glossary = require_file(args.glossary, "glossary") if args.glossary else None
    prompt_path = require_file(args.profile_prompt, "profile prompt") if args.profile_prompt else None
    output_dir = Path(args.output_dir).expanduser().resolve()
    run_record = Path(args.run_record).expanduser().resolve()
    engine = args.engine or shutil.which("pdf2zh_next") or shutil.which("babeldoc")
    if not engine:
        raise SystemExit("No pdf2zh_next or babeldoc executable found. Run doctor.py first.")
    engine_path = str(Path(engine).expanduser().resolve())
    help_result = subprocess.run(
        [engine_path, "--help"], capture_output=True, text=True, timeout=20, check=False
    )
    help_text = (help_result.stdout or "") + "\n" + (help_result.stderr or "")
    if help_result.returncode != 0 or len(help_text.strip()) < 40:
        raise SystemExit(f"Could not inspect engine help for {engine_path}")

    command = [engine_path]
    engine_name = Path(engine_path).name
    is_babeldoc = engine_name == "babeldoc"
    if is_babeldoc:
        files_option = supported(help_text, ("--files",))
        if not files_option:
            raise SystemExit("Installed babeldoc CLI does not expose --files")
        command.extend([files_option, str(pdf)])
    else:
        command.append(str(pdf))

    context_mode = args.context_mode
    backend_metadata: dict[str, str | None] = {"service": None, "bridge_flag": None}
    if args.translation_backend == "google":
        google_option = supported(help_text, ("--google",))
        if google_option:
            command.append(google_option)
            backend_metadata["service"] = "google"
        elif is_babeldoc:
            raise SystemExit(
                "Installed babeldoc CLI does not expose Google translation. "
                "Use pdf2zh_next or select another configured service."
            )
        else:
            # Google is PDFMathTranslate-next's documented default service.
            backend_metadata["service"] = "google-default"
    elif args.translation_backend == "current-agent":
        if not args.agent_translations:
            raise SystemExit("--agent-translations is required for --translation-backend current-agent")
        translations = require_file(args.agent_translations, "Agent translations")
        bridge_option = supported(help_text, AGENT_BRIDGE_OPTIONS)
        if not bridge_option:
            raise SystemExit(
                "The installed PDF engine has no detected pretranslated/custom-translator bridge. "
                "Run select_translation_backend.py for compatibility details; do not silently fall back."
            )
        command.extend([bridge_option, str(translations)])
        context_mode = "current-agent"
        backend_metadata["service"] = "current-agent"
        backend_metadata["bridge_flag"] = bridge_option
    else:
        if not args.configured_service:
            raise SystemExit("--configured-service is required for --translation-backend configured")
        service = args.configured_service.strip().lstrip("-")
        if not service or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", service):
            raise SystemExit("--configured-service must be a safe service flag name")
        if SECRET_OPTION_RE.search(service):
            raise SystemExit("Secret-like configured service names are not accepted")
        service_option = f"--{service}"
        if not supported(help_text, (service_option,)):
            raise SystemExit(f"Installed engine does not expose configured service flag {service_option}")
        command.append(service_option)
        backend_metadata["service"] = service
    add_option(command, help_text, ("--output", "-o", "--output-dir"), str(output_dir), "output")
    add_option(command, help_text, ("--lang-in", "-li", "--source-lang"), args.source_lang, "source language")
    add_option(command, help_text, ("--lang-out", "-lo", "--target-lang"), args.target_lang, "target language")
    add_option(command, help_text, ("--pages", "-p"), args.pages, "page selection")
    if args.max_pages_per_part is not None:
        if args.max_pages_per_part < 1:
            raise SystemExit("--max-pages-per-part must be positive")
        add_option(
            command, help_text, ("--max-pages-per-part",), str(args.max_pages_per_part),
            "maximum pages per part",
        )
    if glossary:
        add_option(
            command, help_text, ("--glossary-files", "--glossaries", "--glossary"),
            str(glossary), "glossary",
        )
    if prompt_path:
        prompt = prompt_path.read_text(encoding="utf-8").strip()
        if len(prompt) > 12000:
            raise SystemExit("Profile prompt exceeds 12,000 characters; make it concise")
        add_option(
            command, help_text, ("--custom-system-prompt", "--prompt"), prompt,
            "custom system prompt",
        )
    if args.ocr:
        option = supported(help_text, ("--auto-enable-ocr-workaround", "--ocr-workaround"))
        if not option:
            raise SystemExit("Installed engine does not expose a supported OCR option")
        command.append(option)
    if args.ignore_cache:
        option = supported(help_text, ("--ignore-cache",))
        if not option:
            raise SystemExit("Installed engine does not expose --ignore-cache")
        command.append(option)

    passthrough = list(passthrough)
    if passthrough and passthrough[0] == "--":
        passthrough = passthrough[1:]
    for index, item in enumerate(passthrough):
        previous = passthrough[index - 1] if index else ""
        if SECRET_OPTION_RE.search(item) or SECRET_OPTION_RE.search(previous):
            raise SystemExit(
                "Secret-like options are not accepted in passthrough args; "
                "use environment variables or a private config"
            )
    command.extend(passthrough)

    output_dir.mkdir(parents=True, exist_ok=True)
    before = {str(path.resolve()) for path in output_dir.glob("**/*") if path.is_file()}
    record = {
        "schema_version": SCHEMA_VERSION,
        "engine": Path(engine_path).name,
        "engine_path": engine_path,
        "engine_help_fingerprint": hashlib.sha256(help_text.encode("utf-8")).hexdigest(),
        "translation_backend": args.translation_backend,
        "translation_backend_details": backend_metadata,
        "context_mode": context_mode,
        "source": {"path": str(pdf), "sha256": sha256_file(pdf)},
        "command": command,
        "executed": args.execute,
        "started_at": None,
        "finished_at": None,
        "returncode": None,
        "outputs": [],
    }
    if not args.execute:
        write_json(run_record, record)
        print(json.dumps(
            {"status": "preview", "command": command, "run_record": str(run_record)},
            ensure_ascii=False, indent=2,
        ))
        return 0

    record["started_at"] = utc_now()
    result = subprocess.run(command, check=False)
    record["finished_at"] = utc_now()
    record["returncode"] = result.returncode
    after = [
        path for path in output_dir.glob("**/*")
        if path.is_file() and str(path.resolve()) not in before
    ]
    record["outputs"] = [
        {"path": str(path.resolve()), "bytes": path.stat().st_size, "sha256": sha256_file(path)}
        for path in sorted(after)
    ]
    write_json(run_record, record)
    print(json.dumps(
        {"status": "finished", "returncode": result.returncode, "outputs": record["outputs"]},
        indent=2,
    ))
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
