---
name: pdf-layout-translation
description: Translate long, layout-sensitive PDF documents with a simple user-facing translation choice—Google by default, the current Agent second, or an already configured service—while PDFMathTranslate-next/BabelDOC automatically handles PDF engineering. Preserve formulas, figures, tables, captions, table-of-contents/index rows and links, page geometry, and protected tokens. Produce both a layout-authoritative translated PDF and an editable Word companion. Use for PDF translation, bilingual or monolingual translated PDFs, broken TOC/index/contents pages, long technical papers/reports/books, terminology-controlled translation, document-level context, translation memory, semantic and visual QA, editable DOCX correction workflows, or retrying only failed PDF pages.
---

# PDF Layout Translation v0.4

Treat PDFMathTranslate-next/BabelDOC as the PDF engineering engine, the language model as the semantic translator, and the agent as the controller for context, terminology, state, QA, and recovery.

## Operating contract

- Preserve the source PDF. Write every intermediate artifact under a task-specific work directory and final files under a separate output directory.
- Never expose API keys in commands, logs, manifests, or prompts. Prefer provider environment variables or an existing config file.
- Never install packages or download model assets without user approval. `doctor.py` is read-only; `setup_environment.py` defaults to a dry run.
- Protect formulas, code, commands, identifiers, URLs, email addresses, DOI values, citations, numbers, units, paths, hashes, and product/model names unless the user explicitly overrides the policy.
- Do not claim pixel-perfect identity. Require semantic checks plus page-by-page visual review before delivery.
- Use the engine translation cache by default. Ignore it only when the translation text itself is known to be wrong.
- Deliver both the translated PDF and an editable DOCX companion unless the user explicitly declines one format. Treat the PDF as layout-authoritative and the DOCX as a correction surface.
- Route detected TOC/index/contents pages through the row-aware TOC pipeline. Do not accept a normal paragraph retry when dot leaders, destination labels, or internal links collapse.
- Present translation choices in this order: **Google translation (default)**, **current Agent model**, then **an already configured third-party or local service**. Do not ask the user to choose between PDFMathTranslate and BabelDOC; those are engineering layers selected automatically.
- Never silently fall back from the current Agent or a configured service to Google. Record the actual backend in `translation-run.json` and disclose it at delivery.

## Select the translation method and execution path

First inspect the installed PDF engine and build the user-facing menu:

```bash
python scripts/select_translation_backend.py \
  --json-out work/<id>/translation-backends.json
```

Offer exactly these primary choices:

1. **Google 翻译（默认）** — fastest setup and no separate API key; requires permission to send document text to Google.
2. **当前 Agent 大模型** — the active Agent translates with the Document Profile, section context, glossary, and TM; layout-preserving PDF output additionally requires a supported reinjection bridge in the installed PDF engine.
3. **已配置的第三方或本地服务** — expand provider names only when the user selects it or already specified one.

If the user expresses no preference, recommend Google, but obtain permission before external document transmission. When the user chooses the current Agent, run the compatibility probe with `--choice current-agent`. If the report says `requires-agent-bridge`, explain that Agent-translated text and the editable Word companion remain possible, but a layout-preserving translated PDF cannot be claimed until a reinjection bridge is available. Do not substitute Google automatically. See [translation backends](references/translation-backends.md).

Use **CLI mode** by default. It is the portable path and supports global profile guidance, glossary injection, engine cache, and QA.

Use **context-aware mode** only when the selected PDFMathTranslate/BabelDOC integration exposes a custom translator or equivalent API hook. Feed the generated context packet to the translator and return only the translation of `current.text`. Do not concatenate neighboring text into the output.

If only the stock CLI is available, record `context_mode: global-profile` in the run manifest. Do not imply that per-segment sliding context was injected. See [context and memory](references/context-memory.md) when context-aware mode is required.

## Workflow

### 1. Create an isolated run directory

Use a structure such as:

```text
work/<document-id>/
  preflight.json
  profile.json
  profile-prompt.txt
  blocks.jsonl
  context-packets.jsonl
  translation-backends.json
  agent-translations.jsonl
  agent-translation-qa.json
  tm.sqlite3
  toc-detection.json
  toc-page-0005.json
  toc-translations-page-0005.json
  toc-render-report-page-0005.json
  toc-qa-page-0005.json
  semantic-qa.json
  terminology-qa.json
  visual-review.json
  qa-manifest.json
  retry-plan.json
  original-pages/
  translated-pages/
output/
  translated.pdf
  translated-editable.docx
  editable-docx-manifest.json
```

### 2. Inspect the environment

Run:

```bash
python scripts/doctor.py --json
```

If the engine or Python dependencies are missing, read [environment setup](references/environment.md), show the proposed action, obtain approval, and then use `setup_environment.py --apply`. Re-run `doctor.py`. Warm up engine assets only after approval.

### 3. Preflight the PDF

Run:

```bash
python scripts/preflight_pdf.py input.pdf --json-out work/<id>/preflight.json
```

Stop and report a blocker when the file cannot be opened or is encrypted without a usable password. For scanned or image-heavy pages, choose the engine's OCR workaround only after reviewing the preflight results. For long documents, use the recommended maximum pages per part.

### 4. Detect and isolate TOC/index pages

Run:

```bash
python scripts/detect_toc.py input.pdf \
  --json-out work/<id>/toc-detection.json
```

When candidate pages are present, read [TOC page handling](references/toc-pages.md). Extract each candidate before normal translation:

```bash
python scripts/extract_toc.py input.pdf --page 5 \
  --json-out work/<id>/toc-page-0005.json \
  --translation-template-out work/<id>/toc-translations-page-0005.json
```

Translate only `heading.target` and row `target` fields. Preserve row IDs, section numbers, destination labels, and protected tokens. Keep each target concise and omit dot leaders/page numbers from the translation.

After the main translated PDF exists, rebuild the candidate page row by row:

```bash
python scripts/render_toc.py \
  --source-pdf input.pdf \
  --base-pdf output/translated-engine.pdf \
  --toc work/<id>/toc-page-0005.json \
  --translations work/<id>/toc-translations-page-0005.json \
  --output output/translated.pdf \
  --report-out work/<id>/toc-render-report-page-0005.json

python scripts/toc_qa.py output/translated.pdf \
  --toc work/<id>/toc-page-0005.json \
  --translations work/<id>/toc-translations-page-0005.json \
  --render-report work/<id>/toc-render-report-page-0005.json \
  --json-out work/<id>/toc-qa-page-0005.json
```

Use the rebuilt file as the translated PDF for all later QA. Verify every TOC row visually. Require unchanged row count, destination labels, row coordinates, page dimensions, and link count.

### 5. Build the Document Profile

Run:

```bash
python scripts/build_document_profile.py input.pdf \
  --profile-out work/<id>/profile.json \
  --blocks-out work/<id>/blocks.jsonl \
  --prompt-out work/<id>/profile-prompt.txt \
  --source-lang en --target-lang zh-CN \
  --glossary assets/glossary-template.csv
```

Review and, when useful, enrich `profile.json` with the inferred domain, audience, register, style constraints, abbreviation decisions, and user-approved terminology. Keep uncertain candidates marked as candidates rather than silently promoting them to fixed glossary entries.

### 6. Build chapter and sliding-window context

Run:

```bash
python scripts/build_context_plan.py \
  --blocks work/<id>/blocks.jsonl \
  --profile work/<id>/profile.json \
  --out work/<id>/context-packets.jsonl \
  --max-current-chars 3500 --previous-blocks 2 --next-blocks 2
```

Each packet contains a stable chunk ID, section identity, previous context, current text, next context, and profile summary. In context-aware mode, send the full packet to the translator but accept output for `current` only. In CLI mode, pass `profile-prompt.txt` as global guidance when supported and let the engine handle segmentation.

When the user selects **当前 Agent 大模型**, initialize a stable translation handoff:

```bash
python scripts/prepare_agent_translations.py init \
  --context work/<id>/context-packets.jsonl \
  --out work/<id>/agent-translations.jsonl
```

The current Agent must fill only each record's `target`, using the matching context packet for meaning and terminology. It must preserve `chunk_id`, `block_ids`, protected tokens, and the source text. Validate before any PDF reinjection:

```bash
python scripts/prepare_agent_translations.py validate \
  --context work/<id>/context-packets.jsonl \
  --translations work/<id>/agent-translations.jsonl \
  --report-out work/<id>/agent-translation-qa.json
```

Stop on incomplete chunks, changed IDs, empty targets, or protected-token loss.

### 7. Initialize and reuse Translation Memory

Initialize a document- or project-scoped memory:

```bash
python scripts/translation_memory.py init work/<id>/tm.sqlite3
```

Import approved prior translations or query candidates before translating a context packet. Store only accepted translations. Never promote machine output to `approved` before QA. See [context and memory](references/context-memory.md) for commands and match policy.

### 8. Run PDF translation

Read [PDFMathTranslate/BabelDOC usage](references/pdfmathtranslate.md), then preview the exact command:

```bash
python scripts/run_translation.py input.pdf \
  --output-dir output \
  --source-lang en --target-lang zh-CN \
  --translation-backend google \
  --glossary project-glossary.csv \
  --profile-prompt work/<id>/profile-prompt.txt \
  --max-pages-per-part 40 \
  --run-record work/<id>/translation-run.json
```

Add `--execute` only after checking the preview and provider configuration. The wrapper discovers the installed CLI's supported flags instead of assuming one release's spelling.

For the current Agent path, replace the backend argument and include the validated handoff:

```bash
--translation-backend current-agent \
--agent-translations work/<id>/agent-translations.jsonl
```

For a service the user already configured, use `--translation-backend configured --configured-service <name>`. Never pass credentials on the command line.

Normalize the engine's monolingual translated output to `output/translated-engine.pdf`. If TOC candidates exist, use that file as the base for step 4 and publish the rebuilt result as `output/translated.pdf`. If no TOC candidate exists, publish the engine output directly as `output/translated.pdf`.

For tables, prefer structural stability over translating every cell. Enable experimental table-text options only when the source and engine version justify them. Preserve raster image contents by default; translating text baked into images is a separate OCR/redraw workflow.

### 9. Run semantic and terminology QA

Run:

```bash
python scripts/semantic_qa.py input.pdf output/translated.pdf \
  --json-out work/<id>/semantic-qa.json

python scripts/terminology_qa.py input.pdf output/translated.pdf \
  --glossary project-glossary.csv \
  --json-out work/<id>/terminology-qa.json
```

Treat page-count changes, missing pages, large text-density loss, and protected-token corruption as blockers or major findings. Treat glossary results as evidence, not proof: inflection, reordering, OCR, and text extraction can create false positives.

### 10. Render and visually inspect every page

Run:

```bash
python scripts/render_pdf.py input.pdf --out-dir work/<id>/original-pages
python scripts/render_pdf.py output/translated.pdf --out-dir work/<id>/translated-pages
python scripts/init_visual_review.py \
  --original-render work/<id>/original-pages/render-manifest.json \
  --translated-render work/<id>/translated-pages/render-manifest.json \
  --out work/<id>/visual-review.json
```

Inspect every page pair for clipping, overlap, missing glyphs, font fallback, formula damage, table breakage, figure displacement/cropping, caption collisions, abnormal whitespace, and header/footer changes. Record the result using the schema in [QA policy](references/qa-policy.md). Sampling is not sufficient for final delivery.

### 11. Build the QA manifest and retry only the smallest failing range

Run:

```bash
python scripts/qa_manifest.py \
  --preflight work/<id>/preflight.json \
  --semantic work/<id>/semantic-qa.json \
  --terminology work/<id>/terminology-qa.json \
  --visual work/<id>/visual-review.json \
  --translation-run work/<id>/translation-run.json \
  --toc-qa work/<id>/toc-qa-page-0005.json \
  --out work/<id>/qa-manifest.json

python scripts/plan_retry.py work/<id>/qa-manifest.json \
  --input input.pdf --output-dir output/retry \
  --source-lang en --target-lang zh-CN \
  --out work/<id>/retry-plan.json
```

Retry only the affected pages or contiguous page ranges. Choose flags from evidence:

- scanned/missing text: OCR workaround;
- table overflow: table translation or conservative layout settings;
- clipping/overlap: typesetting/layout adjustments or shorter approved phrasing;
- terminology drift: corrected glossary or translation-memory entry;
- provider failure: lower concurrency or retry the provider;
- wrong cached translation: ignore cache for the minimal page range.

Re-run all QA checks for replaced pages and regenerate the manifest. Do not deliver while the manifest gate is `fail`.

### 12. Export the editable Word companion

After the PDF passes QA, export an editable, block-addressable DOCX:

```bash
python scripts/export_editable_docx.py output/translated.pdf \
  --output output/translated-editable.docx \
  --manifest-out output/editable-docx-manifest.json \
  --language zh-CN
```

The DOCX uses the compact reference-guide preset. It represents ordinary PDF pages as editable block tables and TOC pages as editable section/title/destination tables. Hidden stable IDs support correction export:

```bash
python scripts/import_docx_corrections.py output/translated-editable.docx \
  --jsonl-out work/<id>/word-corrections.jsonl
```

Render the DOCX to PNG with the available Word/document renderer and inspect every rendered page before delivery. Also reopen it with `python-docx` and confirm that every manifest item and target-language string survives the round trip. If the headless renderer lacks the required CJK font or mapping, verify in native Word or install an approved target-language font; do not mistake a renderer-only missing-glyph preview for deleted DOCX text, and do not claim visual verification until a capable renderer passes. Explain that editing the Word companion does not automatically change PDF geometry; re-import corrections and rerun the affected PDF blocks/pages.

### 13. Deliver

Deliver the requested monolingual and/or bilingual PDF, the editable DOCX companion, the final glossary when useful, and `qa-manifest.json`. Include `editable-docx-manifest.json` when round-trip correction is expected. State the translation method actually used—Google, current Agent, or the named configured service—and summarize any remaining minor findings and any pages that could not be verified visually.

## References

- Read [environment setup](references/environment.md) for dependency and warmup decisions.
- Read [PDFMathTranslate/BabelDOC usage](references/pdfmathtranslate.md) for CLI/API boundaries and version drift.
- Read [translation backends](references/translation-backends.md) before presenting or changing the user-facing translation choices.
- Read [translation policy](references/translation-policy.md) before changing protection or glossary rules.
- Read [context and memory](references/context-memory.md) for packet semantics and TM acceptance rules.
- Read [QA policy](references/qa-policy.md) for severity, visual-review schema, gates, and retry criteria.
- Read [TOC page handling](references/toc-pages.md) whenever an index, contents page, dot leaders, aligned destination labels, or dense internal links appear.
- Read [artifact schemas](references/schemas.md) when integrating these scripts with another agent or pipeline.
