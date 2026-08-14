#!/usr/bin/env python3
"""Export edited Word companion rows to stable-ID JSONL corrections."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from common import SCHEMA_VERSION, require_file, utc_now

ID_RE = re.compile(r"\[\[ID:([^\]]+)\]\]")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("docx")
    parser.add_argument("--jsonl-out", required=True)
    args = parser.parse_args()
    try:
        from docx import Document
    except ImportError as exc:
        raise SystemExit(
            "python-docx is required. Install it with: python -m pip install python-docx"
        ) from exc
    input_path = require_file(args.docx, "DOCX")
    output_path = Path(args.jsonl_out).expanduser().resolve()
    document = Document(input_path)
    records = []
    seen = set()
    for table in document.tables:
        for row in table.rows[1:]:
            if len(row.cells) < 2:
                continue
            id_text = row.cells[0].text
            match = ID_RE.search(id_text)
            if not match:
                continue
            item_id = match.group(1).strip()
            if item_id in seen:
                raise SystemExit(f"Duplicate item ID in DOCX: {item_id}")
            seen.add(item_id)
            corrected_text = row.cells[1].text.strip()
            records.append({
                "schema_version": SCHEMA_VERSION,
                "item_id": item_id,
                "corrected_text": corrected_text,
                "source_docx": str(input_path),
                "extracted_at": utc_now(),
            })
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"Exported {len(records)} corrections to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
