#!/usr/bin/env python3
"""Detect table-of-contents pages that need row-aware translation."""

from __future__ import annotations

import argparse
from pathlib import Path

from common import SCHEMA_VERSION, load_fitz, require_file, sha256_file, utc_now, write_json
from toc_common import analyze_page, detection_score


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf")
    parser.add_argument("--json-out", required=True)
    parser.add_argument("--threshold", type=float, default=0.65)
    args = parser.parse_args()
    if not 0 <= args.threshold <= 1:
        raise SystemExit("--threshold must be between 0 and 1")

    fitz = load_fitz()
    pdf = require_file(args.pdf, "PDF")
    document = fitz.open(pdf)
    if document.needs_pass:
        raise SystemExit(f"PDF requires a password: {pdf}")
    pages = []
    candidates = []
    for index, page in enumerate(document):
        analysis = analyze_page(page, index + 1)
        score = detection_score(analysis)
        item = {
            "page": index + 1,
            "score": score,
            "is_toc_candidate": score >= args.threshold,
            **analysis["metrics"],
            "heading": analysis.get("heading", {}).get("source") if analysis.get("heading") else None,
        }
        pages.append(item)
        if item["is_toc_candidate"]:
            candidates.append(index + 1)
    report = {
        "schema_version": SCHEMA_VERSION,
        "tool": "detect_toc",
        "generated_at": utc_now(),
        "source": {"path": str(pdf), "sha256": sha256_file(pdf), "page_count": len(document)},
        "threshold": args.threshold,
        "candidate_pages": candidates,
        "pages": pages,
    }
    document.close()
    write_json(Path(args.json_out).expanduser().resolve(), report)
    print(f"Detected {len(candidates)} TOC candidate pages: {candidates}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
