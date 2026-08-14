#!/usr/bin/env python3
"""Create a page-complete visual-review scaffold from two render manifests."""

from __future__ import annotations

import argparse
from pathlib import Path

from common import SCHEMA_VERSION, read_json, utc_now, write_json


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original-render", required=True)
    parser.add_argument("--translated-render", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    original_path = Path(args.original_render).expanduser().resolve()
    translated_path = Path(args.translated_render).expanduser().resolve()
    original = read_json(original_path)
    translated = read_json(translated_path)
    original_pages = {int(item["page"]): item for item in original.get("pages", [])}
    translated_pages = {int(item["page"]): item for item in translated.get("pages", [])}
    all_pages = sorted(set(original_pages) | set(translated_pages))
    pages = []
    for page_number in all_pages:
        findings = []
        if page_number not in original_pages or page_number not in translated_pages:
            findings.append({
                "severity": "blocker",
                "code": "rendered-page-missing",
                "message": "One side of the page pair is missing.",
            })
        pages.append({
            "page": page_number,
            "status": "pending" if not findings else "fail",
            "original_image": original_pages.get(page_number, {}).get("file"),
            "translated_image": translated_pages.get(page_number, {}).get("file"),
            "findings": findings,
        })
    review = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now(),
        "reviewed_all_pages": False,
        "reviewer": None,
        "source_manifests": {
            "original": str(original_path),
            "translated": str(translated_path),
        },
        "pages": pages,
    }
    write_json(Path(args.out).expanduser().resolve(), review)
    print(f"Created visual-review scaffold for {len(pages)} pages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
