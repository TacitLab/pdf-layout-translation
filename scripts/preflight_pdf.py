#!/usr/bin/env python3
"""Inspect page geometry, text, images, drawings, links, and scan risk."""

from __future__ import annotations

import argparse
from pathlib import Path

from common import SCHEMA_VERSION, load_fitz, require_file, sha256_file, utc_now, write_json


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf")
    parser.add_argument("--json-out", required=True)
    parser.add_argument("--long-document-pages", type=int, default=50)
    args = parser.parse_args()

    fitz = load_fitz()
    pdf = require_file(args.pdf, "PDF")
    try:
        document = fitz.open(pdf)
    except Exception as exc:
        raise SystemExit(f"Could not open PDF {pdf}: {exc}") from exc
    if document.needs_pass:
        raise SystemExit(f"PDF requires a password: {pdf}")

    pages = []
    scanned_pages: list[int] = []
    blank_pages: list[int] = []
    for index, page in enumerate(document):
        text = page.get_text("text") or ""
        text_chars = len("".join(text.split()))
        images = len(page.get_images(full=True))
        drawings = len(page.get_drawings())
        links = len(page.get_links())
        annotations = 0
        annot = page.first_annot
        while annot:
            annotations += 1
            annot = annot.next
        area = max(float(page.rect.width * page.rect.height), 1.0)
        chars_per_100k_points = round(text_chars / area * 100000, 2)
        likely_scanned = text_chars < 40 and images > 0
        likely_blank = text_chars == 0 and images == 0 and drawings < 3
        page_number = index + 1
        if likely_scanned:
            scanned_pages.append(page_number)
        if likely_blank:
            blank_pages.append(page_number)
        pages.append(
            {
                "page": page_number,
                "width": round(float(page.rect.width), 3),
                "height": round(float(page.rect.height), 3),
                "rotation": int(page.rotation),
                "text_chars": text_chars,
                "chars_per_100k_points": chars_per_100k_points,
                "images": images,
                "drawings": drawings,
                "links": links,
                "annotations": annotations,
                "likely_scanned_or_image_heavy": likely_scanned,
                "likely_blank": likely_blank,
            }
        )

    page_count = len(document)
    report = {
        "schema_version": SCHEMA_VERSION,
        "tool": "preflight_pdf",
        "generated_at": utc_now(),
        "source": {"path": str(pdf), "sha256": sha256_file(pdf), "bytes": pdf.stat().st_size},
        "page_count": page_count,
        "is_long_document": page_count >= args.long_document_pages,
        "recommended_max_pages_per_part": 40 if page_count >= args.long_document_pages else None,
        "scanned_pages": scanned_pages,
        "blank_pages": blank_pages,
        "pages": pages,
        "summary": {
            "scanned_page_count": len(scanned_pages),
            "blank_page_count": len(blank_pages),
            "image_count": sum(page["images"] for page in pages),
            "drawing_count": sum(page["drawings"] for page in pages),
            "text_chars": sum(page["text_chars"] for page in pages),
        },
    }
    document.close()
    write_json(Path(args.json_out).expanduser().resolve(), report)
    print(f"Wrote preflight report: {Path(args.json_out).expanduser().resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

