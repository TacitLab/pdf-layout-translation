#!/usr/bin/env python3
"""Render translated TOC titles row by row and preserve page links."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from common import SCHEMA_VERSION, load_fitz, read_json, require_file, sha256_file, utc_now, write_json

FONT_CANDIDATES = (
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/source-han-sans/SourceHanSansSC-Regular.otf",
)


def color_tuple(fitz: Any, value: int) -> tuple[float, float, float]:
    rgb = fitz.sRGB_to_rgb(value)
    return tuple(component / 255 if component > 1 else float(component) for component in rgb)


def normalize_translations(data: dict[str, Any]) -> tuple[str, dict[str, str]]:
    heading_value = data.get("heading", "")
    if isinstance(heading_value, dict):
        heading = str(heading_value.get("target", "")).strip()
    else:
        heading = str(heading_value).strip()
    rows_value = data.get("rows", [])
    if isinstance(rows_value, dict):
        rows = {str(key): str(value).strip() for key, value in rows_value.items()}
    else:
        rows = {
            str(item["row_id"]): str(item.get("target", "")).strip()
            for item in rows_value
        }
    return heading, rows


def choose_font(fitz: Any, requested: str | None, sample_text: str) -> tuple[str, Any, Path | None]:
    if sample_text.isascii():
        return "helv", fitz.Font("helv"), None
    candidates = [Path(requested).expanduser().resolve()] if requested else []
    candidates.extend(Path(value) for value in FONT_CANDIDATES)
    for candidate in candidates:
        if not candidate.is_file():
            continue
        try:
            font = fitz.Font(fontfile=str(candidate))
        except Exception:
            continue
        return "toc_cjk", font, candidate
    raise SystemExit(
        "A CJK-capable font is required. Pass --font with a TTF, OTF, or supported TTC file."
    )


def clean_link(link: dict[str, Any]) -> dict[str, Any]:
    allowed = ("kind", "from", "page", "to", "zoom", "uri", "file", "name", "nameddest")
    return {key: link[key] for key in allowed if key in link and link[key] is not None}


def replace_links(page: Any, source_links: list[dict[str, Any]]) -> None:
    for link in list(page.get_links()):
        try:
            page.delete_link(link)
        except Exception:
            pass
    for link in source_links:
        page.insert_link(clean_link(link))


def insert_label(
    page: Any,
    point: tuple[float, float],
    text: str,
    font_alias: str,
    font_obj: Any,
    font_size: float,
    max_width: float,
    min_font_size: float,
    color: tuple[float, float, float],
    font_path: Path | None,
) -> tuple[float, float, bool]:
    width = font_obj.text_length(text, fontsize=font_size)
    if width > max_width and width > 0:
        font_size = max(min_font_size, font_size * max_width / width)
        width = font_obj.text_length(text, fontsize=font_size)
    fits = width <= max_width + 0.5
    page.insert_text(
        point, text, fontname=font_alias,
        fontfile=str(font_path) if font_path else None,
        fontsize=font_size, color=color, overlay=True,
    )
    return width, font_size, fits


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-pdf", required=True)
    parser.add_argument("--base-pdf", help="Translated PDF whose TOC page will be replaced")
    parser.add_argument("--toc", required=True)
    parser.add_argument("--translations", required=True)
    parser.add_argument("--font", help="CJK-capable TTF/OTF/TTC")
    parser.add_argument("--min-font-size", type=float, default=6.0)
    parser.add_argument("--output", required=True)
    parser.add_argument("--report-out", required=True)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    fitz = load_fitz()
    source_path = require_file(args.source_pdf, "source PDF")
    base_path = require_file(args.base_pdf, "base PDF") if args.base_pdf else None
    toc_path = require_file(args.toc, "TOC JSON")
    translations_path = require_file(args.translations, "translations JSON")
    output_path = Path(args.output).expanduser().resolve()
    report_path = Path(args.report_out).expanduser().resolve()
    if output_path.exists() and not args.overwrite:
        raise SystemExit(f"Output already exists; pass --overwrite to replace it: {output_path}")
    if args.min_font_size < 4:
        raise SystemExit("--min-font-size must be at least 4")

    toc = read_json(toc_path)
    translations = read_json(translations_path)
    heading_target, targets = normalize_translations(translations)
    page_number = int(toc["page"])
    source_doc = fitz.open(source_path)
    if not 1 <= page_number <= len(source_doc):
        raise SystemExit(f"TOC page {page_number} is outside the source PDF")
    page = source_doc[page_number - 1]
    source_links = list(page.get_links())
    missing = [row["row_id"] for row in toc["rows"] if not targets.get(row["row_id"])]
    if missing:
        raise SystemExit(f"Missing translated TOC targets for {len(missing)} rows: {missing[:8]}")
    protected_failures = []
    for row in toc["rows"]:
        target = targets[row["row_id"]]
        absent = [token for token in row.get("protected_tokens", []) if token not in target]
        if absent:
            protected_failures.append({"row_id": row["row_id"], "missing_tokens": absent})
    if protected_failures:
        raise SystemExit(f"Protected tokens missing from translations: {protected_failures[:5]}")

    text_to_render = heading_target + "".join(targets.values())
    font_alias, font_obj, font_path = choose_font(fitz, args.font, text_to_render)
    if heading_target and toc.get("heading"):
        page.add_redact_annot(fitz.Rect(toc["heading"]["bbox"]), fill=(1, 1, 1))
    for row in toc["rows"]:
        page.add_redact_annot(fitz.Rect(row["rewrite_bbox"]), fill=(1, 1, 1))
    page.apply_redactions()

    findings = []
    rendered_rows = []
    if heading_target and toc.get("heading"):
        heading = toc["heading"]
        heading_size = float(heading.get("font_size", 16))
        page.insert_text(
            (heading["bbox"][0], heading.get("baseline", heading["bbox"][3] - 1)),
            heading_target,
            fontname=font_alias,
            fontfile=str(font_path) if font_path else None,
            fontsize=heading_size,
            color=color_tuple(fitz, int(heading.get("color", 0))),
            overlay=True,
        )
    dot_font = fitz.Font("helv")
    for row in toc["rows"]:
        target = targets[row["row_id"]]
        title_x = float(row["title_bbox"][0])
        destination_x = float(row["destination_bbox"][0])
        baseline = float(row.get("baseline", row["row_bbox"][3] - 1))
        requested_size = float(row.get("font_size", 8.0))
        max_width = max(1.0, destination_x - title_x - 8.0)
        width, used_size, fits = insert_label(
            page, (title_x, baseline), target, font_alias, font_obj,
            requested_size, max_width, args.min_font_size,
            color_tuple(fitz, int(row.get("color", 0))),
            font_path,
        )
        leader_start = title_x + width + 2.0
        leader_width = max(0.0, destination_x - leader_start - 2.0)
        dot_width = dot_font.text_length(".", fontsize=used_size)
        dot_count = max(0, int(leader_width / max(dot_width, 0.1)))
        if dot_count:
            page.insert_text(
                (leader_start, baseline), "." * dot_count,
                fontname="helv", fontsize=used_size, color=(0, 0, 0), overlay=True,
            )
        rendered_rows.append({
            "row_id": row["row_id"],
            "target": target,
            "requested_font_size": requested_size,
            "used_font_size": round(used_size, 3),
            "fits": fits,
            "dot_count": dot_count,
        })
        if not fits:
            findings.append({
                "severity": "major",
                "code": "toc-title-overflow",
                "page": page_number,
                "message": f"TOC target does not fit on one line: {target!r}",
                "row_id": row["row_id"],
            })
    replace_links(page, source_links)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if base_path:
        base_doc = fitz.open(base_path)
        if len(base_doc) != len(source_doc):
            raise SystemExit("Base and source PDFs must have the same page count")
        base_page = base_doc[page_number - 1]
        if abs(base_page.rect.width - page.rect.width) > 1 or abs(base_page.rect.height - page.rect.height) > 1:
            raise SystemExit("Base and source TOC page dimensions do not match")
        for link in list(base_page.get_links()):
            try:
                base_page.delete_link(link)
            except Exception:
                pass
        base_page.add_redact_annot(base_page.rect, fill=(1, 1, 1))
        base_page.apply_redactions()
        base_page.show_pdf_page(base_page.rect, source_doc, page_number - 1, overlay=True)
        replace_links(base_page, source_links)
        # Avoid aggressive object-table garbage collection here. Some valid PDFs with
        # dense destination trees trigger PyMuPDF failures at garbage levels 3-4.
        base_doc.save(output_path, garbage=0, deflate=True)
        base_doc.close()
    else:
        source_doc.save(output_path, garbage=0, deflate=True)
    source_doc.close()

    verified = fitz.open(output_path)
    output_links = len(verified[page_number - 1].get_links())
    verified.close()
    if output_links != len(source_links):
        findings.append({
            "severity": "blocker",
            "code": "toc-link-loss",
            "page": page_number,
            "message": f"Expected {len(source_links)} links, found {output_links}.",
        })
    report = {
        "schema_version": SCHEMA_VERSION,
        "tool": "render_toc",
        "generated_at": utc_now(),
        "page": page_number,
        "inputs": {
            "source_pdf": {"path": str(source_path), "sha256": sha256_file(source_path)},
            "base_pdf": (
                {"path": str(base_path), "sha256": sha256_file(base_path)} if base_path else None
            ),
            "toc": str(toc_path),
            "translations": str(translations_path),
        },
        "output": {"path": str(output_path), "sha256": sha256_file(output_path)},
        "font": {"alias": font_alias, "path": str(font_path) if font_path else None},
        "source_link_count": len(source_links),
        "output_link_count": output_links,
        "rows": rendered_rows,
        "findings": findings,
        "summary": {
            "rows_rendered": len(rendered_rows),
            "rows_fit": sum(1 for row in rendered_rows if row["fits"]),
            "success": not findings,
        },
    }
    write_json(report_path, report)
    print(json.dumps(report["summary"], indent=2))
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
