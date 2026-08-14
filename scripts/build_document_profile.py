#!/usr/bin/env python3
"""Build a deterministic Document Profile and stable PDF text blocks."""

from __future__ import annotations

import argparse
import collections
import csv
import re
import statistics
from pathlib import Path
from typing import Any

from common import (
    SCHEMA_VERSION,
    load_fitz,
    normalize_space,
    require_file,
    sha256_file,
    stable_id,
    utc_now,
    write_json,
    write_jsonl,
)

TOKEN_PATTERNS = {
    "url": re.compile(r"https?://[^\s<>]+"),
    "email": re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b"),
    "doi": re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.I),
    "number": re.compile(r"(?<!\w)[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?(?!\w)"),
    "path": re.compile(r"(?:^|\s)(?:[A-Za-z]:\\|/)[^\s,;]+"),
}


def load_glossary(path: Path | None) -> list[dict[str, str]]:
    if path is None:
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not {"source", "target"}.issubset(reader.fieldnames):
            raise SystemExit("Glossary must contain source and target columns")
        return [
            {key: (value or "").strip() for key, value in row.items()}
            for row in reader
            if (row.get("source") or "").strip()
        ]


def extract_blocks(document: Any) -> tuple[list[dict[str, Any]], list[float]]:
    blocks: list[dict[str, Any]] = []
    sizes: list[float] = []
    for page_index, page in enumerate(document):
        page_dict = page.get_text("dict", sort=True)
        order = 0
        for raw_block in page_dict.get("blocks", []):
            if raw_block.get("type") != 0:
                continue
            lines = raw_block.get("lines", [])
            text_parts: list[str] = []
            span_sizes: list[float] = []
            fonts: list[str] = []
            for line in lines:
                line_text = "".join(span.get("text", "") for span in line.get("spans", []))
                if line_text.strip():
                    text_parts.append(line_text)
                for span in line.get("spans", []):
                    if span.get("text", "").strip():
                        span_sizes.append(float(span.get("size", 0.0)))
                        fonts.append(str(span.get("font", "")))
            text = normalize_space("\n".join(text_parts))
            if not text:
                continue
            order += 1
            size = statistics.median(span_sizes) if span_sizes else 0.0
            sizes.extend(span_sizes)
            page_number = page_index + 1
            block_id = f"p{page_number:04d}-b{order:04d}"
            blocks.append(
                {
                    "schema_version": SCHEMA_VERSION,
                    "block_id": block_id,
                    "page": page_number,
                    "order": order,
                    "section_id": None,
                    "kind": "paragraph",
                    "bbox": [round(float(value), 3) for value in raw_block.get("bbox", (0, 0, 0, 0))],
                    "font_size": round(size, 3),
                    "fonts": sorted(set(fonts)),
                    "text": text,
                }
            )
    return blocks, sizes


def classify_sections(blocks: list[dict[str, Any]], body_size: float) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    current_id = "sec-0000"
    sections.append({"id": current_id, "title": "Front matter", "page": 1, "confidence": 0.2})
    heading_number = 0
    heading_re = re.compile(r"^(?:\d+(?:\.\d+)*[.)]?\s+|[A-Z][A-Z\s:&/-]{3,}|(?:Abstract|Introduction|Methods?|Results?|Discussion|Conclusion|References)\b)", re.I)
    for block in blocks:
        text = block["text"]
        font_size = float(block.get("font_size", 0.0))
        bold = any("bold" in font.lower() for font in block.get("fonts", []))
        short = len(text) <= 140 and text.count(".") <= 2
        likely_heading = short and (
            font_size >= body_size + 1.2 or (bold and font_size >= body_size) or bool(heading_re.match(text))
        )
        if likely_heading:
            heading_number += 1
            current_id = f"sec-{heading_number:04d}"
            confidence = 0.9 if font_size >= body_size + 1.2 else 0.65
            sections.append(
                {
                    "id": current_id,
                    "title": text[:200],
                    "page": block["page"],
                    "block_id": block["block_id"],
                    "confidence": confidence,
                }
            )
            block["kind"] = "heading"
        block["section_id"] = current_id
    return sections


def term_candidates(text: str, limit: int) -> list[dict[str, Any]]:
    counter: collections.Counter[str] = collections.Counter()
    patterns = [
        re.compile(r"\b(?:[A-Z][A-Za-z0-9-]+(?:\s+|$)){2,5}"),
        re.compile(r"\b[A-Z][A-Z0-9-]{2,}\b"),
    ]
    for pattern in patterns:
        for match in pattern.finditer(text):
            candidate = normalize_space(match.group(0)).strip(".,;:()[]")
            if 2 <= len(candidate) <= 100:
                counter[candidate] += 1
    return [
        {"source": term, "count": count, "status": "candidate", "target": None}
        for term, count in counter.most_common(limit)
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf")
    parser.add_argument("--profile-out", required=True)
    parser.add_argument("--blocks-out", required=True)
    parser.add_argument("--prompt-out", required=True)
    parser.add_argument("--source-lang", required=True)
    parser.add_argument("--target-lang", required=True)
    parser.add_argument("--glossary")
    parser.add_argument("--document-id")
    parser.add_argument("--domain", default="unknown; review required")
    parser.add_argument("--audience", default="match the source document")
    parser.add_argument("--register", default="professional and faithful")
    parser.add_argument("--term-limit", type=int, default=80)
    args = parser.parse_args()

    fitz = load_fitz()
    pdf = require_file(args.pdf, "PDF")
    glossary_path = require_file(args.glossary, "glossary") if args.glossary else None
    glossary = load_glossary(glossary_path)
    document = fitz.open(pdf)
    if document.needs_pass:
        raise SystemExit(f"PDF requires a password: {pdf}")
    blocks, sizes = extract_blocks(document)
    body_size = statistics.median(sizes) if sizes else 10.0
    sections = classify_sections(blocks, body_size)
    all_text = "\n".join(block["text"] for block in blocks)
    protected_summary = {}
    protected_examples = {}
    for name, pattern in TOKEN_PATTERNS.items():
        values = pattern.findall(all_text)
        protected_summary[name] = len(values)
        protected_examples[name] = values[:10]
    document_id = args.document_id or stable_id("doc", sha256_file(pdf), length=16)
    profile = {
        "schema_version": SCHEMA_VERSION,
        "document_id": document_id,
        "source": {
            "path": str(pdf),
            "sha256": sha256_file(pdf),
            "page_count": len(document),
        },
        "languages": {"source": args.source_lang, "target": args.target_lang},
        "statistics": {
            "block_count": len(blocks),
            "text_chars": len(all_text),
            "median_font_size": round(body_size, 3),
        },
        "sections": sections,
        "style": {
            "domain": args.domain,
            "audience": args.audience,
            "register": args.register,
            "faithfulness": "preserve meaning, qualification, negation, numbers, and references",
            "uncertain_terms": "keep consistent and expose for review",
        },
        "glossary": glossary,
        "term_candidates": term_candidates(all_text, args.term_limit),
        "protected_token_summary": protected_summary,
        "protected_token_examples": protected_examples,
        "provenance": {
            "generated_at": utc_now(),
            "generator": "build_document_profile.py",
            "method": "deterministic PDF text and font heuristics; agent review required",
        },
    }
    write_json(Path(args.profile_out).expanduser().resolve(), profile)
    write_jsonl(Path(args.blocks_out).expanduser().resolve(), blocks)
    prompt_lines = [
        f"Translate from {args.source_lang} to {args.target_lang}.",
        f"Domain: {args.domain}.",
        f"Audience: {args.audience}.",
        f"Register: {args.register}.",
        "Preserve formulas, code, commands, identifiers, URLs, email addresses, DOI values, citations, numbers, units, paths, hashes, and model names.",
        "Keep terminology consistent across sections. Preserve qualification, negation, modality, references, and figure/table numbering.",
    ]
    if glossary:
        prompt_lines.append("Use these approved term mappings when applicable:")
        for row in glossary[:100]:
            prompt_lines.append(f"- {row['source']} => {row['target']}")
    prompt_out = Path(args.prompt_out).expanduser().resolve()
    prompt_out.parent.mkdir(parents=True, exist_ok=True)
    prompt_out.write_text("\n".join(prompt_lines) + "\n", encoding="utf-8")
    document.close()
    print(f"Wrote profile, {len(blocks)} blocks, and prompt for {document_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

