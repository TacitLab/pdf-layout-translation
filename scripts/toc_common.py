#!/usr/bin/env python3
"""Shared table-of-contents detection and row extraction helpers."""

from __future__ import annotations

import re
from typing import Any, Iterable

from common import SCHEMA_VERSION, normalize_space, stable_id

LEADER_RE = re.compile(r"\.{8,}")
SECTION_RE = re.compile(r"^\d+(?:\.\d+)*\.?$")
PAGE_LABEL_RE = re.compile(r"^(?:\d+(?:-\d+)?|[ivxlcdm]+)$", re.I)
HEADING_RE = re.compile(
    r"^(?:index|contents|table\s+of\s+contents|目录|目錄|索引)$", re.I
)


def rect_list(rect: Any) -> list[float]:
    return [round(float(rect.x0), 3), round(float(rect.y0), 3),
            round(float(rect.x1), 3), round(float(rect.y1), 3)]


def union_bbox(items: Iterable[dict[str, Any]]) -> list[float]:
    values = list(items)
    return [
        round(min(item["x0"] for item in values), 3),
        round(min(item["y0"] for item in values), 3),
        round(max(item["x1"] for item in values), 3),
        round(max(item["y1"] for item in values), 3),
    ]


def group_words(page: Any, tolerance: float = 2.1) -> list[list[dict[str, Any]]]:
    raw_words = page.get_text("words", sort=True)
    words = []
    for item in raw_words:
        text = str(item[4])
        if not text.strip():
            continue
        base = {
            "x0": float(item[0]), "y0": float(item[1]),
            "x1": float(item[2]), "y1": float(item[3]),
            "text": text, "block": int(item[5]),
            "line": int(item[6]), "word": int(item[7]),
            "center_y": (float(item[1]) + float(item[3])) / 2,
        }
        leader_match = LEADER_RE.search(text)
        if not leader_match or (leader_match.start() == 0 and leader_match.end() == len(text)):
            words.append(base)
            continue
        # PyMuPDF can merge the final title token and regenerated leaders into one
        # extracted word. Split it virtually so the same row parser works before
        # and after reconstruction. Approximate x positions are sufficient because
        # the authoritative destination geometry remains a separate word.
        parts = [text[:leader_match.start()], leader_match.group(0), text[leader_match.end():]]
        total_units = max(1, sum(len(part) for part in parts))
        cursor = base["x0"]
        for part_index, part in enumerate(parts):
            if not part:
                continue
            width = (base["x1"] - base["x0"]) * len(part) / total_units
            virtual = dict(base)
            virtual["text"] = part
            virtual["x0"] = cursor
            virtual["x1"] = base["x1"] if part_index == len(parts) - 1 else cursor + width
            virtual["word"] = base["word"] * 10 + part_index
            words.append(virtual)
            cursor += width
    rows: list[list[dict[str, Any]]] = []
    centers: list[float] = []
    for word in sorted(words, key=lambda item: (item["center_y"], item["x0"])):
        best_index = None
        best_delta = None
        for index in range(max(0, len(rows) - 4), len(rows)):
            delta = abs(word["center_y"] - centers[index])
            if delta <= tolerance and (best_delta is None or delta < best_delta):
                best_index = index
                best_delta = delta
        if best_index is None:
            rows.append([word])
            centers.append(word["center_y"])
        else:
            rows[best_index].append(word)
            centers[best_index] = sum(item["center_y"] for item in rows[best_index]) / len(rows[best_index])
    return [sorted(row, key=lambda item: item["x0"]) for row in rows]


def page_spans(page: Any) -> list[dict[str, Any]]:
    spans = []
    for block in page.get_text("dict", sort=True).get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = str(span.get("text", ""))
                if not text.strip():
                    continue
                bbox = span.get("bbox", (0, 0, 0, 0))
                origin = span.get("origin", (bbox[0], bbox[3]))
                spans.append({
                    "text": text,
                    "bbox": [float(value) for value in bbox],
                    "origin": [float(value) for value in origin],
                    "size": float(span.get("size", 8.0)),
                    "font": str(span.get("font", "")),
                    "color": int(span.get("color", 0)),
                })
    return spans


def overlap_y(a: list[float], b: list[float]) -> float:
    return max(0.0, min(a[3], b[3]) - max(a[1], b[1]))


def matching_style(row_bbox: list[float], title_x: float, spans: list[dict[str, Any]]) -> dict[str, Any]:
    candidates = [
        span for span in spans
        if overlap_y(row_bbox, span["bbox"]) > 0
        and span["bbox"][2] >= title_x - 1
    ]
    if not candidates:
        return {"font_size": max(6.0, row_bbox[3] - row_bbox[1]), "font": "", "color": 0,
                "baseline": row_bbox[3] - 1}
    candidate = min(candidates, key=lambda span: abs(span["bbox"][0] - title_x))
    return {
        "font_size": round(candidate["size"], 3),
        "font": candidate["font"],
        "color": candidate["color"],
        "baseline": round(candidate["origin"][1], 3),
    }


def protected_tokens(text: str) -> list[str]:
    values = []
    title_has_lowercase = any(character.islower() for character in text)
    for token in re.findall(r"[A-Za-z][A-Za-z0-9/-]*", text):
        mixed_case_identifier = any(
            re.search(r"[a-z][A-Z]", part) for part in re.split(r"[-/]", token)
        )
        has_digit_or_slash = bool(re.search(r"[0-9/]", token))
        hyphen_acronym = "-" in token and all(
            part.isupper() and len(part) <= 5 for part in token.split("-") if part
        )
        short_acronym = title_has_lowercase and token.isupper() and 2 <= len(token) <= 5
        if mixed_case_identifier or has_digit_or_slash or hyphen_acronym or short_acronym:
            values.append(token)
    return sorted(set(values), key=lambda value: text.find(value))


def analyze_page(page: Any, page_number: int) -> dict[str, Any]:
    rows = group_words(page)
    spans = page_spans(page)
    links = page.get_links()
    extracted_rows = []
    heading = None
    for words in rows:
        row_bbox = union_bbox(words)
        row_text = normalize_space(" ".join(word["text"] for word in words))
        if heading is None and row_bbox[1] < page.rect.height * 0.2 and HEADING_RE.match(row_text):
            style = matching_style(row_bbox, row_bbox[0], spans)
            heading = {
                "source": row_text,
                "bbox": row_bbox,
                **style,
            }
        leader_indexes = [index for index, word in enumerate(words) if LEADER_RE.search(word["text"])]
        if not leader_indexes:
            continue
        leader_index = leader_indexes[0]
        page_index = None
        for index in range(len(words) - 1, leader_index, -1):
            if PAGE_LABEL_RE.match(words[index]["text"]):
                page_index = index
                break
        if page_index is None:
            continue
        section_index = 0 if SECTION_RE.match(words[0]["text"]) else None
        title_start = 1 if section_index == 0 else 0
        title_words = words[title_start:leader_index]
        if not title_words:
            continue
        section_number = words[0]["text"] if section_index == 0 else ""
        title = normalize_space(" ".join(word["text"] for word in title_words))
        title_bbox = union_bbox(title_words)
        leader_bbox = union_bbox(words[index] for index in leader_indexes)
        page_word = words[page_index]
        rewrite_bbox = [
            round(title_bbox[0] - 0.8, 3),
            round(min(title_bbox[1], leader_bbox[1]) - 0.8, 3),
            round(page_word["x0"] - 2.0, 3),
            round(max(title_bbox[3], leader_bbox[3]) + 0.8, 3),
        ]
        style = matching_style(row_bbox, title_bbox[0], spans)
        center_y = (row_bbox[1] + row_bbox[3]) / 2
        matching_links = [
            rect_list(link["from"]) for link in links
            if "from" in link
            and float(link["from"].y0) - 2 <= center_y <= float(link["from"].y1) + 2
        ]
        row_id = stable_id(
            "toc", page_number, section_number, title, page_word["text"], length=14
        )
        extracted_rows.append({
            "row_id": row_id,
            "page": page_number,
            "section_number": section_number,
            "level": max(1, section_number.rstrip(".").count(".") + 1) if section_number else 1,
            "source_title": title,
            "protected_tokens": protected_tokens(title),
            "destination_label": page_word["text"],
            "row_bbox": row_bbox,
            "title_bbox": title_bbox,
            "leader_bbox": leader_bbox,
            "destination_bbox": [
                round(page_word["x0"], 3), round(page_word["y0"], 3),
                round(page_word["x1"], 3), round(page_word["y1"], 3),
            ],
            "rewrite_bbox": rewrite_bbox,
            "matching_link_rects": matching_links,
            **style,
        })
    right_edge_rows = sum(
        1 for row in extracted_rows
        if row["destination_bbox"][0] >= page.rect.width * 0.75
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "page": page_number,
        "width": round(float(page.rect.width), 3),
        "height": round(float(page.rect.height), 3),
        "heading": heading,
        "rows": extracted_rows,
        "metrics": {
            "text_line_groups": len(rows),
            "dot_leader_rows": len(extracted_rows),
            "right_aligned_destination_rows": right_edge_rows,
            "link_count": len(links),
        },
    }


def detection_score(analysis: dict[str, Any]) -> float:
    metrics = analysis["metrics"]
    leader_rows = metrics["dot_leader_rows"]
    score = 0.0
    if leader_rows >= 8:
        score += 0.55
    elif leader_rows >= 4:
        score += 0.3
    if metrics["right_aligned_destination_rows"] >= 8:
        score += 0.2
    if metrics["link_count"] >= 8:
        score += 0.15
    if analysis.get("heading"):
        score += 0.2
    return round(min(score, 1.0), 3)
