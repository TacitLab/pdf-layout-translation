#!/usr/bin/env python3
"""Merge semantic, terminology, visual, preflight, and run evidence into one QA gate."""

from __future__ import annotations

import argparse
import collections
from pathlib import Path
from typing import Any

from common import SCHEMA_VERSION, read_json, stable_id, utc_now, write_json


def load_report(path_value: str, expected_tool: str | None = None) -> tuple[Path, dict[str, Any]]:
    path = Path(path_value).expanduser().resolve()
    if not path.is_file():
        raise SystemExit(f"Report not found: {path}")
    report = read_json(path)
    if expected_tool and report.get("tool") != expected_tool:
        raise SystemExit(f"Expected {expected_tool} report at {path}, got {report.get('tool')!r}")
    return path, report


def normalize_findings(report_name: str, report: dict[str, Any]) -> list[dict[str, Any]]:
    normalized = []
    for item in report.get("findings", []):
        finding = dict(item)
        finding["source_report"] = report_name
        finding["finding_id"] = stable_id(
            "finding", report_name, finding.get("page", ""), finding.get("code", ""),
            finding.get("message", ""),
        )
        normalized.append(finding)
    return normalized


def visual_findings(report: dict[str, Any]) -> list[dict[str, Any]]:
    flattened = []
    for page in report.get("pages", []):
        for item in page.get("findings", []):
            finding = dict(item)
            finding.setdefault("page", page.get("page"))
            flattened.append(finding)
    return flattened


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight", required=True)
    parser.add_argument("--semantic", required=True)
    parser.add_argument("--terminology", required=True)
    parser.add_argument("--visual", required=True)
    parser.add_argument("--translation-run", required=True)
    parser.add_argument("--toc-qa", action="append", default=[], help="Optional repeatable TOC QA report")
    parser.add_argument("--waivers", help="Optional JSON file with a waivers array")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    preflight_path, preflight = load_report(args.preflight, "preflight_pdf")
    semantic_path, semantic = load_report(args.semantic, "semantic_qa")
    terminology_path, terminology = load_report(args.terminology, "terminology_qa")
    visual_path, visual = load_report(args.visual)
    run_path, translation_run = load_report(args.translation_run)
    toc_reports = [load_report(value, "toc_qa") for value in args.toc_qa]
    if "pages" not in visual:
        raise SystemExit("Visual review must contain a pages array")

    visual_copy = dict(visual)
    visual_copy["findings"] = visual_findings(visual)
    findings = []
    findings.extend(normalize_findings("semantic", semantic))
    findings.extend(normalize_findings("terminology", terminology))
    findings.extend(normalize_findings("visual", visual_copy))
    for toc_path, toc_report in toc_reports:
        findings.extend(normalize_findings(f"toc:{toc_path.name}", toc_report))
    if translation_run.get("executed") and translation_run.get("returncode") != 0:
        findings.extend(normalize_findings("translation-run", {
            "findings": [{
                "severity": "blocker",
                "code": "translation-command-failed",
                "message": f"Translation engine exited with status {translation_run.get('returncode')}.",
            }]
        }))

    waivers = []
    if args.waivers:
        waiver_path = Path(args.waivers).expanduser().resolve()
        waiver_data = read_json(waiver_path)
        waivers = waiver_data.get("waivers", [])
    waived_ids = {item.get("finding_id") for item in waivers if item.get("finding_id")}
    active = [item for item in findings if item["finding_id"] not in waived_ids]
    counts = collections.Counter(item.get("severity", "unknown") for item in active)

    expected_pages = int(preflight.get("page_count", 0))
    reviewed_pages = {int(page["page"]) for page in visual.get("pages", []) if page.get("page")}
    visual_complete = (
        bool(visual.get("reviewed_all_pages"))
        and expected_pages > 0
        and reviewed_pages == set(range(1, expected_pages + 1))
    )
    if counts["blocker"] or counts["major"]:
        gate = "fail"
    elif not visual_complete:
        gate = "incomplete"
    elif counts["minor"]:
        gate = "pass_with_minor"
    else:
        gate = "pass"

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "gate": gate,
        "generated_at": utc_now(),
        "inputs": {
            "preflight": str(preflight_path),
            "semantic": str(semantic_path),
            "terminology": str(terminology_path),
            "visual": str(visual_path),
            "translation_run": str(run_path),
            "toc_qa": [str(path) for path, _ in toc_reports],
        },
        "translation": {
            "engine": translation_run.get("engine"),
            "backend": translation_run.get("translation_backend"),
            "context_mode": translation_run.get("context_mode"),
            "returncode": translation_run.get("returncode"),
            "outputs": translation_run.get("outputs", []),
        },
        "coverage": {
            "expected_pages": expected_pages,
            "visual_pages_recorded": sorted(reviewed_pages),
            "reviewed_all_pages_claim": bool(visual.get("reviewed_all_pages")),
            "visual_complete": visual_complete,
        },
        "summary": {
            "active_findings": len(active),
            "waived_findings": len(findings) - len(active),
            "by_severity": dict(counts),
        },
        "findings": findings,
        "waivers": waivers,
    }
    write_json(Path(args.out).expanduser().resolve(), manifest)
    print(f"QA gate: {gate}; active findings: {len(active)}")
    return 0 if gate in {"pass", "pass_with_minor"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
