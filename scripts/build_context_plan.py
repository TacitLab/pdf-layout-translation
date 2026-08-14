#!/usr/bin/env python3
"""Build chapter-aware sliding-window context packets from stable PDF blocks."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from common import SCHEMA_VERSION, read_json, read_jsonl, stable_id, write_jsonl


def compact(block: dict[str, Any]) -> dict[str, Any]:
    return {
        "block_id": block["block_id"],
        "page": block["page"],
        "kind": block.get("kind", "paragraph"),
        "text": block["text"],
    }


def build_chunks(blocks: list[dict[str, Any]], max_chars: int) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []
    current_chars = 0
    current_section = None
    for block in blocks:
        section = block.get("section_id") or "sec-0000"
        text_length = len(block.get("text", ""))
        boundary = current and section != current_section
        too_large = current and current_chars + text_length + 1 > max_chars
        if boundary or too_large:
            chunks.append({"section_id": current_section, "blocks": current})
            current = []
            current_chars = 0
        current_section = section
        current.append(block)
        current_chars += text_length + 1
    if current:
        chunks.append({"section_id": current_section, "blocks": current})
    return chunks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blocks", required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--max-current-chars", type=int, default=3500)
    parser.add_argument("--previous-blocks", type=int, default=2)
    parser.add_argument("--next-blocks", type=int, default=2)
    args = parser.parse_args()
    if args.max_current_chars < 200:
        raise SystemExit("--max-current-chars must be at least 200")
    if min(args.previous_blocks, args.next_blocks) < 0:
        raise SystemExit("Context block counts cannot be negative")

    blocks = read_jsonl(Path(args.blocks).expanduser().resolve())
    profile = read_json(Path(args.profile).expanduser().resolve())
    sections = {section["id"]: section for section in profile.get("sections", [])}
    chunks = build_chunks(blocks, args.max_current_chars)
    packets: list[dict[str, Any]] = []
    flat_index = {block["block_id"]: index for index, block in enumerate(blocks)}
    for ordinal, chunk in enumerate(chunks, 1):
        chunk_blocks = chunk["blocks"]
        first_index = flat_index[chunk_blocks[0]["block_id"]]
        last_index = flat_index[chunk_blocks[-1]["block_id"]]
        previous = blocks[max(0, first_index - args.previous_blocks) : first_index]
        following = blocks[last_index + 1 : last_index + 1 + args.next_blocks]
        current_text = "\n".join(block["text"] for block in chunk_blocks)
        section_id = str(chunk["section_id"])
        chunk_id = stable_id("chunk", section_id, *(block["block_id"] for block in chunk_blocks))
        packets.append(
            {
                "schema_version": SCHEMA_VERSION,
                "chunk_id": chunk_id,
                "ordinal": ordinal,
                "section": sections.get(section_id, {"id": section_id, "title": "Unknown"}),
                "previous": [compact(block) for block in previous],
                "current": {
                    "block_ids": [block["block_id"] for block in chunk_blocks],
                    "pages": sorted({block["page"] for block in chunk_blocks}),
                    "text": current_text,
                },
                "next": [compact(block) for block in following],
                "profile": {
                    "document_id": profile.get("document_id"),
                    "source_lang": profile.get("languages", {}).get("source"),
                    "target_lang": profile.get("languages", {}).get("target"),
                    "style": profile.get("style", {}),
                },
                "output_contract": "Return only the translation of current.text; do not translate or echo context.",
            }
        )
    write_jsonl(Path(args.out).expanduser().resolve(), packets)
    print(f"Wrote {len(packets)} context packets")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
