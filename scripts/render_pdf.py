#!/usr/bin/env python3
"""Render every PDF page to PNG and write a render manifest."""

from __future__ import annotations

import argparse
from pathlib import Path

from common import SCHEMA_VERSION, load_fitz, require_file, sha256_file, utc_now, write_json


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--dpi", type=int, default=144)
    args = parser.parse_args()
    if not 72 <= args.dpi <= 600:
        raise SystemExit("--dpi must be between 72 and 600")

    fitz = load_fitz()
    pdf = require_file(args.pdf, "PDF")
    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    document = fitz.open(pdf)
    scale = args.dpi / 72.0
    matrix = fitz.Matrix(scale, scale)
    rendered = []
    for index, page in enumerate(document):
        pixmap = page.get_pixmap(matrix=matrix, alpha=False)
        output = out_dir / f"page-{index + 1:04d}.png"
        pixmap.save(output)
        rendered.append(
            {
                "page": index + 1,
                "file": output.name,
                "width_px": pixmap.width,
                "height_px": pixmap.height,
            }
        )
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "tool": "render_pdf",
        "generated_at": utc_now(),
        "source": {"path": str(pdf), "sha256": sha256_file(pdf)},
        "dpi": args.dpi,
        "page_count": len(rendered),
        "pages": rendered,
    }
    write_json(out_dir / "render-manifest.json", manifest)
    document.close()
    print(f"Rendered {len(rendered)} pages to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
