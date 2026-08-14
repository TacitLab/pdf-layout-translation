#!/usr/bin/env python3
"""Plan minimal page-range retries from an unwaived QA manifest."""

from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path
from typing import Any

from common import SCHEMA_VERSION, page_ranges, read_json, utc_now, write_json


def recommendations(codes: set[str]) -> tuple[list[str], list[str]]:
    options: list[str] = []
    actions: list[str] = []
    if any(code in codes for code in {"text-density-loss", "missing-text", "scanned-page"}):
        options.append("--ocr")
        actions.append("Verify the page is scanned or has a broken text layer before enabling OCR.")
    if any(code.startswith(("preferred-term", "number-token", "url-token", "email-token", "doi-token")) for code in codes):
        options.append("--ignore-cache")
        actions.append("Correct the glossary or approved translation memory before bypassing cache.")
    if any(code in codes for code in {"caption-overlap", "text-overlap", "text-clipping", "table-overflow"}):
        actions.append("Adjust only supported typesetting/table options after inspecting the installed engine help.")
    if any(code.startswith("toc-") for code in codes):
        actions.append(
            "Route this page through detect_toc.py, extract_toc.py, render_toc.py, and toc_qa.py; "
            "do not retry it as a normal paragraph page."
        )
    if "page-dimension-change" in codes:
        actions.append("Do not merge this page until source and translated page geometry match.")
    return sorted(set(options)), actions


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--source-lang", required=True)
    parser.add_argument("--target-lang", required=True)
    parser.add_argument("--glossary")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    manifest_path = Path(args.manifest).expanduser().resolve()
    if not manifest_path.is_file():
        raise SystemExit(f"Manifest not found: {manifest_path}")
    manifest = read_json(manifest_path)
    waived = {item.get("finding_id") for item in manifest.get("waivers", [])}
    retryable = [
        item for item in manifest.get("findings", [])
        if item.get("finding_id") not in waived
        and item.get("severity") in {"blocker", "major"}
        and isinstance(item.get("page"), int)
    ]
    manual = [
        item for item in manifest.get("findings", [])
        if item.get("finding_id") not in waived
        and item.get("severity") in {"blocker", "major"}
        and not isinstance(item.get("page"), int)
    ]
    by_page: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for item in retryable:
        by_page[int(item["page"])].append(item)

    groups = []
    ordered_pages = sorted(by_page)
    cursor = 0
    while cursor < len(ordered_pages):
        group_pages = [ordered_pages[cursor]]
        cursor += 1
        while cursor < len(ordered_pages) and ordered_pages[cursor] == group_pages[-1] + 1:
            group_pages.append(ordered_pages[cursor])
            cursor += 1
        group_findings = [finding for page in group_pages for finding in by_page[page]]
        codes = {str(item.get("code", "unknown")) for item in group_findings}
        options, actions = recommendations(codes)
        page_spec = ",".join(page_ranges(group_pages))
        run_record = Path(args.output_dir).expanduser().resolve() / f"retry-{page_spec.replace(',', '_')}.json"
        command = [
            "python", "scripts/run_translation.py", str(Path(args.input).expanduser().resolve()),
            "--output-dir", str(Path(args.output_dir).expanduser().resolve()),
            "--source-lang", args.source_lang,
            "--target-lang", args.target_lang,
            "--pages", page_spec,
            "--run-record", str(run_record),
        ]
        if args.glossary:
            command.extend(["--glossary", str(Path(args.glossary).expanduser().resolve())])
        command.extend(options)
        groups.append({
            "pages": group_pages,
            "page_spec": page_spec,
            "reasons": sorted(codes),
            "finding_ids": [item["finding_id"] for item in group_findings],
            "recommended_options": options,
            "manual_checks": actions,
            "preview_command": command,
        })

    plan = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now(),
        "source_manifest": str(manifest_path),
        "retry_groups": groups,
        "manual_actions": [{
            "finding_id": item.get("finding_id"),
            "code": item.get("code"),
            "message": item.get("message"),
            "reason": "Finding is not scoped to a single page; diagnose before retrying.",
        } for item in manual],
        "execution_note": "Commands are previews. Verify flags against the installed engine, then add --execute.",
    }
    write_json(Path(args.out).expanduser().resolve(), plan)
    print(f"Planned {len(groups)} retry groups; {len(manual)} manual findings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
