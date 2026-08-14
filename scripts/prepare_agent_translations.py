#!/usr/bin/env python3
"""Initialize or validate translations produced directly by the current Agent."""

from __future__ import annotations

import argparse
import collections
import re
from pathlib import Path
from typing import Any

from common import SCHEMA_VERSION, read_jsonl, require_file, utc_now, write_json, write_jsonl

PROTECTED_RE = re.compile(
    r"https?://\S+|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|\b\d+(?:\.\d+)?%?\b|"
    r"\b[A-Za-z]+(?:[A-Z][A-Za-z0-9]*)+[A-Za-z0-9]*\b|\b[A-Z]{2,6}\b"
)


def protected(text: str) -> list[str]:
    return sorted(set(PROTECTED_RE.findall(text)), key=text.find)


def initialize(context_path: Path, output_path: Path) -> int:
    packets = read_jsonl(context_path)
    records = []
    for packet in packets:
        current = packet.get("current", {})
        source = str(current.get("text", ""))
        records.append({
            "schema_version": SCHEMA_VERSION,
            "provider": "current-agent",
            "chunk_id": packet.get("chunk_id"),
            "block_ids": current.get("block_ids", []),
            "source": source,
            "target": "",
            "protected_tokens": protected(source),
            "status": "draft",
        })
    write_jsonl(output_path, records)
    print(f"Initialized {len(records)} Agent translation records")
    return 0


def validate(context_path: Path, translations_path: Path, report_path: Path) -> int:
    packets = read_jsonl(context_path)
    translations = read_jsonl(translations_path)
    expected = {str(item.get("chunk_id")): item for item in packets}
    actual: dict[str, dict[str, Any]] = {}
    findings = []
    for item in translations:
        chunk_id = str(item.get("chunk_id", ""))
        if not chunk_id:
            findings.append({"severity": "blocker", "code": "agent-chunk-id-missing", "message": "A translation record has no chunk_id."})
            continue
        if chunk_id in actual:
            findings.append({"severity": "blocker", "code": "agent-chunk-id-duplicate", "message": f"Duplicate chunk_id: {chunk_id}"})
        actual[chunk_id] = item
    for chunk_id, packet in expected.items():
        item = actual.get(chunk_id)
        if not item:
            findings.append({"severity": "blocker", "code": "agent-translation-missing", "message": f"Missing Agent translation for {chunk_id}."})
            continue
        current = packet.get("current", {})
        target = str(item.get("target", "")).strip()
        if not target:
            findings.append({"severity": "blocker", "code": "agent-target-empty", "message": f"Empty Agent translation for {chunk_id}."})
        if item.get("block_ids") != current.get("block_ids"):
            findings.append({"severity": "blocker", "code": "agent-block-id-change", "message": f"Block IDs changed for {chunk_id}."})
        absent = [token for token in protected(str(current.get("text", ""))) if token not in target]
        if absent:
            findings.append({
                "severity": "major", "code": "agent-protected-token-loss",
                "message": f"Protected tokens missing for {chunk_id}.",
                "evidence": {"tokens": absent},
            })
    for chunk_id in sorted(set(actual) - set(expected)):
        findings.append({"severity": "major", "code": "agent-translation-extra", "message": f"Unexpected Agent translation: {chunk_id}."})
    counts = collections.Counter(item["severity"] for item in findings)
    report = {
        "schema_version": SCHEMA_VERSION,
        "tool": "prepare_agent_translations",
        "generated_at": utc_now(),
        "inputs": {"context": str(context_path), "translations": str(translations_path)},
        "summary": {
            "expected": len(expected), "received": len(actual),
            "complete": not counts["blocker"] and not counts["major"],
            "findings": dict(counts),
        },
        "findings": findings,
    }
    write_json(report_path, report)
    print(f"Validated {len(actual)} Agent translations with {len(findings)} findings")
    return 1 if counts["blocker"] or counts["major"] else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    init_parser = subparsers.add_parser("init")
    init_parser.add_argument("--context", required=True)
    init_parser.add_argument("--out", required=True)
    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("--context", required=True)
    validate_parser.add_argument("--translations", required=True)
    validate_parser.add_argument("--report-out", required=True)
    args = parser.parse_args()
    context_path = require_file(args.context, "context packets")
    if args.command == "init":
        return initialize(context_path, Path(args.out).expanduser().resolve())
    translations_path = require_file(args.translations, "Agent translations")
    return validate(context_path, translations_path, Path(args.report_out).expanduser().resolve())


if __name__ == "__main__":
    raise SystemExit(main())
