# TOC and index page handling

## Why ordinary paragraph translation fails

A table of contents is a positioned data structure, not an ordinary paragraph. PDF extractors often return dozens of visual rows as only a few large text blocks. Literal dot leaders, section numbers, destination labels, and internal links then enter translation as one stream and the translated text collapses into long paragraphs.

Treat contents, index, outline, and similar navigation pages as a separate page class.

## Detection signals

Route a page through the TOC pipeline when several of these signals agree:

- a contents-like heading such as `INDEX`, `CONTENTS`, or `TABLE OF CONTENTS`;
- at least four rows ending in compact page or destination labels;
- repeated dot leaders;
- strong vertical alignment of destination labels;
- dense internal link annotations;
- many visual text lines but only a few extracted paragraph blocks.

Detection is advisory. Visually confirm borderline candidates before replacing a page.

## Row-aware workflow

1. Run `detect_toc.py` over the PDF.
2. Run `extract_toc.py` for each confirmed candidate.
3. Translate only `source_title` into `target_title` in the generated template.
4. Run `render_toc.py` to redact and redraw title and leader regions row by row.
5. Run `toc_qa.py` and visually inspect the rebuilt page at full size.

Never send the whole contents page to the normal paragraph translation path after it has been classified as TOC.

## Translation template contract

Keep every `row_id` unchanged. Keep `section_number`, `destination_label`, and protected tokens unchanged. Translate titles concisely enough to fit one line. Do not type dot leaders into `target_title`; the renderer regenerates them from row geometry.

If a title contains a model name, mixed-case identifier, acronym, or product token, preserve it exactly unless the approved glossary explicitly changes it.

## Links and destinations

Preserve the original page object whenever possible so inbound PDF destinations remain valid. Restore the original link annotations after redaction. A rebuilt page must retain the source page dimensions, row count, destination labels, and link count.

## Fonts and fitting

Use a font that contains all target-language glyphs. For Chinese output, prefer an installed CJK font such as PingFang, Songti, Microsoft YaHei, or Noto Sans CJK. The renderer may reduce a title slightly within the configured minimum size, but it must not wrap a row or move its destination label.

If a translated title still cannot fit, shorten the translation using the glossary and document style. If it remains unsafe, keep that row in the source language and record a major QA finding rather than corrupting the navigation layout.

## Fallback

When row extraction is ambiguous, links cannot be preserved, or the page remains unreadable after one targeted retry, retain the original TOC page and disclose the exception. The original navigable page is preferable to a translated but structurally broken page.
