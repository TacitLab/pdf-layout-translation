# QA policy

## Severity

`blocker` prevents delivery: unreadable output, page-count mismatch, missing page, major content loss, broken formula, cropped figure, corrupted file, collapsed TOC rows, lost TOC destination labels, or broken internal navigation links.

`major` normally requires retry: clipped/overlapping paragraph, table overflow, caption collision, widespread missing glyphs, protected-token mutation, material terminology drift, large text-density loss, TOC title overflow, or material TOC row-coordinate drift.

`minor` may be delivered with disclosure: harmless line-break changes, small spacing shifts, slight font-size changes within policy, or a localized stylistic inconsistency.

## Visual-review file

Record every page, including pages with no finding:

```json
{
  "schema_version": "0.4",
  "reviewed_all_pages": true,
  "reviewer": "agent-vision",
  "pages": [
    {"page": 1, "status": "pass", "findings": []},
    {
      "page": 2,
      "status": "fail",
      "findings": [
        {
          "severity": "major",
          "code": "caption-overlap",
          "message": "Translated caption overlaps the lower edge of Figure 1."
        }
      ]
    }
  ]
}
```

Set `reviewed_all_pages` to true only after checking every original/translated page pair.

## Automated checks

Semantic QA checks page count, dimensions, text density, protected numeric tokens, URLs, email addresses, DOI values, and likely text loss. Terminology QA compares source-term occurrence with preferred-target occurrence by page.

For every detected TOC page, run `toc_qa.py` and include its report in `qa_manifest.py` with `--toc-qa`. Require unchanged row count, destination labels, page dimensions, and link count, then visually inspect every row at full size.

For the editable Word companion, verify both representations: render every DOCX page and reopen the DOCX to compare its stable IDs and Unicode text with `editable-docx-manifest.json`. A headless renderer can lack CJK fonts or character maps even when the DOCX text is intact. In that case, use native Word or an approved font-enabled renderer before claiming visual QA; retain the text-level result only as diagnostic evidence.

Automated checks are heuristics. They cannot replace visual review or bilingual semantic judgment.

## Manifest gate

The manifest gate is:

- `fail` if any blocker exists;
- `fail` if any major finding exists unless explicitly waived with a reason;
- `incomplete` if visual review is absent or does not cover every page;
- `pass_with_minor` if only minor findings remain;
- `pass` when no finding remains.

Do not silently waive findings. A waiver must identify the finding, owner, rationale, and date.

## Retry

Group adjacent failing pages only when they share a plausible cause. Preserve cache for layout retries. Bypass cache for the smallest possible range when correcting translation text. Re-run semantic, terminology, and visual QA after replacement or merge.
