#!/usr/bin/env python3
"""Check preferred glossary targets against source-term occurrences by page."""

from __future__ import annotations

import argparse
import collections
import csv
import re
from pathlib import Path
from typing import Any

from common import SCHEMA_VERSION, load_fitz, require_file, sha256_file, utc_now, write_json


def load_glossary(path: Path, target_lang: str | None) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not {"source", "target"}.issubset(reader.fieldnames):
            raise SystemExit("Glossary must contain source and target columns")
        entries = []
        for line_number, row in enumerate(reader, 2):
            source = (row.get("source") or "").strip()
            target = (row.get("target") or "").strip()
            entry_lang = (row.get("tgt_lng") or "").strip()
            if not source or not target:
                raise SystemExit(f"Empty source or target in glossary line {line_number}")
            if target_lang and entry_lang and entry_lang.replace("-", "_").casefold() != target_lang.replace("-", "_").casefold():
                continue
            entries.append({
                "source": source,
                "target": target,
                "tgt_lng": entry_lang,
                "notes": (row.get("notes") or "").strip(),
            })
    conflicts: dict[str, set[str]] = collections.defaultdict(set)
    for entry in entries:
        conflicts[entry["source"].casefold()].add(entry["target"])
    bad = {source: sorted(targets) for source, targets in conflicts.items() if len(targets) > 1}
    if bad:
        raise SystemExit(f"Conflicting glossary targets: {bad}")
    return entries


def count_phrase(text: str, phrase: str) -> int:
    escaped = re.escape(phrase)
    if phrase.isascii() and re.fullmatch(r"[\w -]+", phrase, flags=re.UNICODE):
        pattern = rf"(?<!\w){escaped}(?!\w)"
    else:
        pattern = escaped
    return len(re.findall(pattern, text, flags=re.I))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("original")
    parser.add_argument("translated")
    parser.add_argument("--glossary", required=True)
    parser.add_argument("--target-lang")
    parser.add_argument("--json-out", required=True)
    args = parser.parse_args()

    fitz = load_fitz()
    original_path = require_file(args.original, "original PDF")
    translated_path = require_file(args.translated, "translated PDF")
    glossary_path = require_file(args.glossary, "glossary")
    entries = load_glossary(glossary_path, args.target_lang)
    original = fitz.open(original_path)
    translated = fitz.open(translated_path)
    page_count = min(len(original), len(translated))
    findings: list[dict[str, Any]] = []
    coverage = []
    for entry in entries:
        source_total = 0
        target_total = 0
        missing_pages = []
        for index in range(page_count):
            source_text = original[index].get_text("text") or ""
            target_text = translated[index].get_text("text") or ""
            source_count = count_phrase(source_text, entry["source"])
            target_count = count_phrase(target_text, entry["target"])
            source_total += source_count
            target_total += target_count
            if source_count and not target_count:
                missing_pages.append(index + 1)
                findings.append({
                    "severity": "major",
                    "code": "preferred-term-missing",
                    "page": index + 1,
                    "message": f"Source term {entry['source']!r} occurs but preferred target {entry['target']!r} was not extracted.",
                    "evidence": {"source_count": source_count, "target_count": target_count},
                    "term": entry,
                })
        coverage.append({
            "source": entry["source"],
            "target": entry["target"],
            "source_occurrences": source_total,
            "target_occurrences": target_total,
            "missing_pages": missing_pages,
        })
    counts = collections.Counter(item["severity"] for item in findings)
    report = {
        "schema_version": SCHEMA_VERSION,
        "tool": "terminology_qa",
        "generated_at": utc_now(),
        "inputs": {
            "original": {"path": str(original_path), "sha256": sha256_file(original_path)},
            "translated": {"path": str(translated_path), "sha256": sha256_file(translated_path)},
            "glossary": {"path": str(glossary_path), "sha256": sha256_file(glossary_path)},
        },
        "summary": {
            "terms_checked": len(entries),
            "pages_checked": page_count,
            "findings": dict(counts),
            "heuristic_warning": "PDF text extraction and inflection can create false positives; review evidence.",
        },
        "coverage": coverage,
        "findings": findings,
    }
    original.close()
    translated.close()
    write_json(Path(args.json_out).expanduser().resolve(), report)
    print(f"Wrote terminology QA with {len(findings)} findings")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
