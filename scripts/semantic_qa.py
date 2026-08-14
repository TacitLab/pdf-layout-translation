#!/usr/bin/env python3
"""Compare original and translated PDFs for structural and protected-token drift."""

from __future__ import annotations

import argparse
import collections
import re
from pathlib import Path
from typing import Any

from common import SCHEMA_VERSION, load_fitz, require_file, sha256_file, utc_now, write_json

PATTERNS = {
    "url": re.compile(r"https?://[^\s<>]+"),
    "email": re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b"),
    "doi": re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.I),
    "number": re.compile(r"(?<!\w)[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?(?!\w)"),
}


def tokens(text: str) -> dict[str, collections.Counter[str]]:
    return {
        name: collections.Counter(value.rstrip(".,;:)") for value in pattern.findall(text))
        for name, pattern in PATTERNS.items()
    }


def finding(
    severity: str,
    code: str,
    message: str,
    page: int | None = None,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    value: dict[str, Any] = {"severity": severity, "code": code, "message": message}
    if page is not None:
        value["page"] = page
    if evidence:
        value["evidence"] = evidence
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("original")
    parser.add_argument("translated")
    parser.add_argument("--json-out", required=True)
    parser.add_argument("--density-ratio-major", type=float, default=0.35)
    parser.add_argument("--dimension-tolerance", type=float, default=1.0)
    args = parser.parse_args()
    if not 0 < args.density_ratio_major < 1:
        raise SystemExit("--density-ratio-major must be between 0 and 1")

    fitz = load_fitz()
    original_path = require_file(args.original, "original PDF")
    translated_path = require_file(args.translated, "translated PDF")
    original = fitz.open(original_path)
    translated = fitz.open(translated_path)
    findings: list[dict[str, Any]] = []
    if len(original) != len(translated):
        findings.append(finding(
            "blocker", "page-count-mismatch",
            f"Original has {len(original)} pages; translated has {len(translated)} pages.",
            evidence={"original": len(original), "translated": len(translated)},
        ))

    page_reports = []
    shared_pages = min(len(original), len(translated))
    for index in range(shared_pages):
        page_number = index + 1
        source_page = original[index]
        target_page = translated[index]
        source_text = source_page.get_text("text") or ""
        target_text = target_page.get_text("text") or ""
        source_chars = len("".join(source_text.split()))
        target_chars = len("".join(target_text.split()))
        density_ratio = target_chars / max(source_chars, 1)
        page_findings: list[dict[str, Any]] = []
        width_delta = abs(float(source_page.rect.width - target_page.rect.width))
        height_delta = abs(float(source_page.rect.height - target_page.rect.height))
        if width_delta > args.dimension_tolerance or height_delta > args.dimension_tolerance:
            page_findings.append(finding(
                "major", "page-dimension-change", "Page dimensions changed beyond tolerance.",
                page_number,
                {"width_delta": round(width_delta, 3), "height_delta": round(height_delta, 3)},
            ))
        if source_chars >= 100 and density_ratio < args.density_ratio_major:
            page_findings.append(finding(
                "major", "text-density-loss",
                f"Translated text density is {density_ratio:.2%} of the source extraction.",
                page_number,
                {"source_chars": source_chars, "target_chars": target_chars, "ratio": round(density_ratio, 6)},
            ))
        source_tokens = tokens(source_text)
        target_tokens = tokens(target_text)
        for token_type, source_counter in source_tokens.items():
            target_counter = target_tokens[token_type]
            missing = list((source_counter - target_counter).elements())
            added = list((target_counter - source_counter).elements())
            if missing or added:
                severity = "major" if token_type in {"url", "email", "doi"} else "minor"
                page_findings.append(finding(
                    severity, f"{token_type}-token-drift",
                    f"Protected {token_type} tokens differ between source and translation.",
                    page_number,
                    {"missing": missing[:30], "added": added[:30]},
                ))
        findings.extend(page_findings)
        page_reports.append({
            "page": page_number,
            "source_text_chars": source_chars,
            "translated_text_chars": target_chars,
            "density_ratio": round(density_ratio, 6),
            "finding_count": len(page_findings),
        })

    counts = collections.Counter(item["severity"] for item in findings)
    report = {
        "schema_version": SCHEMA_VERSION,
        "tool": "semantic_qa",
        "generated_at": utc_now(),
        "inputs": {
            "original": {"path": str(original_path), "sha256": sha256_file(original_path)},
            "translated": {"path": str(translated_path), "sha256": sha256_file(translated_path)},
        },
        "summary": {
            "original_pages": len(original),
            "translated_pages": len(translated),
            "shared_pages_checked": shared_pages,
            "findings": dict(counts),
        },
        "pages": page_reports,
        "findings": findings,
    }
    original.close()
    translated.close()
    write_json(Path(args.json_out).expanduser().resolve(), report)
    print(f"Wrote semantic QA with {len(findings)} findings")
    return 1 if counts["blocker"] or counts["major"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

