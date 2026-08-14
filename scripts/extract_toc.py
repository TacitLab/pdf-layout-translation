#!/usr/bin/env python3
"""Extract one TOC page into stable rows and a translation template."""

from __future__ import annotations

import argparse
from pathlib import Path

from common import SCHEMA_VERSION, load_fitz, require_file, sha256_file, utc_now, write_json
from toc_common import analyze_page, detection_score


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf")
    parser.add_argument("--page", type=int, required=True, help="One-based page number")
    parser.add_argument("--json-out", required=True)
    parser.add_argument("--translation-template-out", required=True)
    args = parser.parse_args()

    fitz = load_fitz()
    pdf = require_file(args.pdf, "PDF")
    document = fitz.open(pdf)
    if not 1 <= args.page <= len(document):
        raise SystemExit(f"--page must be between 1 and {len(document)}")
    analysis = analyze_page(document[args.page - 1], args.page)
    analysis.update({
        "tool": "extract_toc",
        "generated_at": utc_now(),
        "source": {"path": str(pdf), "sha256": sha256_file(pdf)},
        "detection_score": detection_score(analysis),
        "source_link_count": analysis["metrics"]["link_count"],
    })
    if len(analysis["rows"]) < 4:
        raise SystemExit(f"Page {args.page} does not contain enough TOC rows")
    template = {
        "schema_version": SCHEMA_VERSION,
        "page": args.page,
        "heading": {
            "source": analysis.get("heading", {}).get("source", ""),
            "target": "",
        },
        "rows": [
            {
                "row_id": row["row_id"],
                "section_number": row["section_number"],
                "source": row["source_title"],
                "target": "",
                "destination_label": row["destination_label"],
                "protected_tokens": row["protected_tokens"],
            }
            for row in analysis["rows"]
        ],
        "translation_contract": [
            "Translate target fields only.",
            "Preserve row_id, section_number, destination_label, and protected_tokens exactly.",
            "Keep each target concise enough for one TOC line.",
            "Do not add dot leaders or page numbers to target.",
        ],
    }
    document.close()
    write_json(Path(args.json_out).expanduser().resolve(), analysis)
    write_json(Path(args.translation_template_out).expanduser().resolve(), template)
    print(f"Extracted {len(analysis['rows'])} TOC rows from page {args.page}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
