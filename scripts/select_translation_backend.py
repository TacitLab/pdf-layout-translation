#!/usr/bin/env python3
"""Present user-facing translation choices and probe PDF reinjection support."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Iterable

from common import SCHEMA_VERSION, utc_now, write_json


AGENT_BRIDGE_OPTIONS = (
    "--translations-jsonl",
    "--translation-map",
    "--pretranslated-jsonl",
    "--custom-translator",
    "--translator-callback",
)
CONFIGURED_SERVICES = (
    "openai", "deepseek", "deepl", "ollama", "azure", "gemini",
    "siliconflow", "bing", "tencent", "zhipu", "qwen", "anthropic",
)


def exposed(help_text: str, names: Iterable[str]) -> str | None:
    for name in names:
        if re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", help_text):
            return name
    return None


def inspect_engine(explicit: str | None) -> dict[str, object]:
    engine = explicit or shutil.which("pdf2zh_next") or shutil.which("babeldoc")
    if not engine:
        return {"found": False, "path": None, "name": None, "help": "", "error": "not found"}
    path = str(Path(engine).expanduser().resolve())
    try:
        result = subprocess.run(
            [path, "--help"], capture_output=True, text=True, timeout=20, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"found": True, "path": path, "name": Path(path).name, "help": "", "error": str(exc)}
    help_text = (result.stdout or "") + "\n" + (result.stderr or "")
    return {
        "found": True,
        "path": path,
        "name": Path(path).name,
        "help": help_text,
        "error": None if result.returncode == 0 else f"help exited {result.returncode}",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", help="Explicit pdf2zh_next or babeldoc executable")
    parser.add_argument(
        "--choice", choices=("google", "current-agent", "configured"),
        help="Option selected by the user",
    )
    parser.add_argument("--allow-text-only", action="store_true", help="Allow Agent output without PDF reinjection")
    parser.add_argument("--json-out", required=True)
    args = parser.parse_args()

    engine = inspect_engine(args.engine)
    help_text = str(engine["help"])
    engine_name = str(engine["name"] or "")
    google_flag = exposed(help_text, ("--google",))
    google_ready = bool(engine["found"] and (google_flag or engine_name == "pdf2zh_next"))
    bridge_flag = exposed(help_text, AGENT_BRIDGE_OPTIONS)
    configured_flags = [
        f"--{service}" for service in CONFIGURED_SERVICES
        if exposed(help_text, (f"--{service}",))
    ]
    options = [
        {
            "order": 1,
            "id": "google",
            "label": "Google 翻译（默认）",
            "available_for_pdf": google_ready,
            "requires_separate_credentials": False,
            "requires_network": True,
            "engine_flag": google_flag,
            "note": "速度快、无需单独配置 API Key；文档文本会发送到 Google。",
        },
        {
            "order": 2,
            "id": "current-agent",
            "label": "当前 Agent 大模型",
            "available_for_text": True,
            "available_for_pdf": bool(engine["found"] and bridge_flag),
            "requires_separate_credentials": False,
            "requires_network": None,
            "engine_flag": bridge_flag,
            "note": (
                "由当前 Agent 使用 Document Profile、章节上下文、术语表和翻译记忆生成译文；"
                "布局 PDF 还要求已安装引擎提供译文回填接口。"
            ),
        },
        {
            "order": 3,
            "id": "configured",
            "label": "已配置的第三方或本地服务",
            "available_for_pdf": bool(configured_flags),
            "requires_separate_credentials": None,
            "requires_network": None,
            "engine_flags": configured_flags,
            "note": "仅在用户已配置服务或明确要求具体提供商时展开技术选项。",
        },
    ]
    status = "menu"
    selected = next((item for item in options if item["id"] == args.choice), None)
    exit_code = 0
    if selected:
        if args.choice == "current-agent" and not selected["available_for_pdf"]:
            status = "text-only" if args.allow_text_only else "requires-agent-bridge"
            exit_code = 0 if args.allow_text_only else 2
        elif not selected.get("available_for_pdf"):
            status = "unavailable"
            exit_code = 2
        else:
            status = "ready"
    report = {
        "schema_version": SCHEMA_VERSION,
        "tool": "select_translation_backend",
        "generated_at": utc_now(),
        "engine": {key: value for key, value in engine.items() if key != "help"},
        "options": options,
        "selected": args.choice,
        "status": status,
        "policy": {
            "default": "google",
            "do_not_silently_fallback": True,
            "engineering_layer_is_not_a_user_choice": True,
        },
    }
    write_json(Path(args.json_out).expanduser().resolve(), report)
    print(json.dumps({"status": status, "options": options}, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
