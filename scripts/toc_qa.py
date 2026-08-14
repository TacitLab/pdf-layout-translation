#!/usr/bin/env python3
"""Verify TOC row structure, translated titles, page labels, and links."""

from __future__ import annotations

import argparse
import collections
from pathlib import Path
from typing import Any

from common import SCHEMA_VERSION, load_fitz, normalize_space, read_json, require_file, sha256_file, utc_now, write_json
from toc_common import analyze_page


def translations_by_id(data: dict[str, Any]) -> tuple[str, dict[str, str]]:
    heading_value = data.get("heading", "")
    heading = (
        str(heading_value.get("target", "")).strip()
        if isinstance(heading_value, dict) else str(heading_value).strip()
    )
    rows_value = data.get("rows", [])
    if isinstance(rows_value, dict):
        rows = {str(key): str(value).strip() for key, value in rows_value.items()}
    else:
        rows = {str(item["row_id"]): str(item.get("target", "")).strip() for item in rows_value}
    return heading, rows


def add(findings: list[dict[str, Any]], severity: str, code: str, message: str, page: int,
        evidence: dict[str, Any] | None = None) -> None:
    item: dict[str, Any] = {
        "severity": severity, "code": code, "message": message, "page": page,
    }
    if evidence:
        item["evidence"] = evidence
    findings.append(item)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf")
    parser.add_argument("--toc", required=True)
    parser.add_argument("--translations", required=True)
    parser.add_argument("--render-report")
    parser.add_argument("--json-out", required=True)
    parser.add_argument("--coordinate-tolerance", type=float, default=2.5)
    args = parser.parse_args()

    fitz = load_fitz()
    pdf_path = require_file(args.pdf, "PDF")
    toc_path = require_file(args.toc, "TOC JSON")
    translations_path = require_file(args.translations, "translations JSON")
    toc = read_json(toc_path)
    translations = read_json(translations_path)
    heading_target, targets = translations_by_id(translations)
    page_number = int(toc["page"])
    document = fitz.open(pdf_path)
    if not 1 <= page_number <= len(document):
        raise SystemExit(f"TOC page {page_number} is outside the PDF")
    page = document[page_number - 1]
    analysis = analyze_page(page, page_number)
    findings: list[dict[str, Any]] = []
    if len(analysis["rows"]) != len(toc["rows"]):
        add(
            findings, "blocker", "toc-row-count-mismatch",
            f"Expected {len(toc['rows'])} TOC rows, extracted {len(analysis['rows'])}.",
            page_number,
        )
    if analysis["metrics"]["link_count"] != int(toc.get("source_link_count", 0)):
        add(
            findings, "blocker", "toc-link-loss",
            f"Expected {toc.get('source_link_count', 0)} links, found {analysis['metrics']['link_count']}.",
            page_number,
        )
    if heading_target:
        page_text = normalize_space(page.get_text("text") or "")
        if normalize_space(heading_target) not in page_text:
            add(findings, "major", "toc-heading-missing", "Translated TOC heading was not extracted.", page_number)

    output_by_key = {
        (row["section_number"], row["destination_label"]): row for row in analysis["rows"]
    }
    for source_row in toc["rows"]:
        key = (source_row["section_number"], source_row["destination_label"])
        output_row = output_by_key.get(key)
        if not output_row:
            add(
                findings, "blocker", "toc-row-missing",
                f"TOC row {key} is missing after rendering.", page_number,
                {"row_id": source_row["row_id"]},
            )
            continue
        target = normalize_space(targets.get(source_row["row_id"], ""))
        if target and target not in normalize_space(output_row["source_title"]):
            add(
                findings, "major", "toc-target-missing",
                f"Translated title was not extracted for TOC row {key}.", page_number,
                {"row_id": source_row["row_id"], "target": target,
                 "extracted": output_row["source_title"]},
            )
        y_delta = abs(float(output_row["row_bbox"][1]) - float(source_row["row_bbox"][1]))
        destination_x_delta = abs(
            float(output_row["destination_bbox"][0]) - float(source_row["destination_bbox"][0])
        )
        if y_delta > args.coordinate_tolerance:
            add(
                findings, "major", "toc-row-position-drift",
                f"TOC row {key} moved vertically by {y_delta:.2f} pt.", page_number,
            )
        if destination_x_delta > args.coordinate_tolerance:
            add(
                findings, "major", "toc-page-number-drift",
                f"Destination label for TOC row {key} moved by {destination_x_delta:.2f} pt.",
                page_number,
            )
    if args.render_report:
        render_report = read_json(require_file(args.render_report, "render report"))
        for finding in render_report.get("findings", []):
            copied = dict(finding)
            copied["source_report"] = "render_toc"
            findings.append(copied)
    counts = collections.Counter(item["severity"] for item in findings)
    report = {
        "schema_version": SCHEMA_VERSION,
        "tool": "toc_qa",
        "generated_at": utc_now(),
        "inputs": {
            "pdf": {"path": str(pdf_path), "sha256": sha256_file(pdf_path)},
            "toc": str(toc_path),
            "translations": str(translations_path),
        },
        "page": page_number,
        "summary": {
            "expected_rows": len(toc["rows"]),
            "extracted_rows": len(analysis["rows"]),
            "expected_links": int(toc.get("source_link_count", 0)),
            "extracted_links": analysis["metrics"]["link_count"],
            "findings": dict(counts),
        },
        "findings": findings,
    }
    document.close()
    write_json(Path(args.json_out).expanduser().resolve(), report)
    print(f"Wrote TOC QA with {len(findings)} findings")
    return 1 if counts["blocker"] or counts["major"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
