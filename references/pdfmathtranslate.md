# PDFMathTranslate-next and BabelDOC

## Responsibility boundary

PDFMathTranslate-next is the product shell and reference integration. BabelDOC is the layout-aware engine. Let them parse pages, identify layout, protect formulas, typeset, and write PDFs. The user selects a translation method, not one of these engineering layers. Do not recreate the PDF intermediate representation with ad hoc span replacement unless the engine cannot process the document.

The agent owns environment decisions, document profile, glossary, optional context packets, translation memory, run records, semantic/visual QA, and minimal retry planning.

## Translation-method boundary

Use Google as the first/default choice for PDFMathTranslate-next. The wrapper adds `--google` when the installed release exposes it and otherwise relies on PDFMathTranslate-next's documented Google default. A bare BabelDOC CLI is not assumed to provide Google.

The current Agent is the second user-facing choice. It can translate context packets directly, but layout-preserving PDF output is ready only when the installed engine exposes a pretranslated-map or custom-translator bridge. Probe this capability first. The Agent's active model is not automatically an API endpoint or credential that may be handed to a subprocess.

Show individual third-party/local provider names only under the third choice. Never silently substitute one method for another.

## Version drift

The CLI evolves. Glossary options, output options, OCR flags, page selection, and prompt flags may differ between releases. Always inspect `pdf2zh_next --help` (or `babeldoc --help`) in the installed environment.

`run_translation.py` detects supported flag spellings for:

- source and target language;
- output directory;
- page selection;
- maximum pages per part;
- glossary files;
- custom system prompt;
- OCR workaround;
- cache bypass.
- Google/default, current-Agent bridge, or an explicitly configured service.

If a requested feature is not exposed by the installed CLI, the wrapper stops instead of silently dropping it.

## Glossary CSV format

BabelDOC's glossary loader reads only the `source` and `target` columns (`tgt_lng` is optional); every other column, such as `notes`, is ignored. Extra columns do not cause errors, so the skill's four-column template works as-is. "Preserve, do not translate" is expressed as `target` equal to `source` (see the `Pod,Pod` row in `assets/glossary-template.csv`). Do not invent other encodings for protected terms.

## Context modes

### Global-profile CLI mode

Pass the concise profile prompt through the installed CLI's custom-system-prompt option when supported. Pass a validated glossary through the installed glossary option. Preserve the engine cache. Record `global-profile` as the context mode.

This improves global terminology and style, but it is not paragraph-level sliding context.

### Context-aware translator mode

Use a supported custom translator/API hook to translate each context packet. Give the model:

- document profile summary;
- section identity;
- previous blocks;
- current block;
- next blocks;
- applicable glossary entries;
- approved TM matches.

Require a translation of the current block only. Maintain stable chunk IDs and store accepted source/target pairs in the TM. Then return translated segments to BabelDOC through the supported integration point.

Do not patch private BabelDOC internals without pinning and testing the exact engine version.

### Current-Agent handoff mode

Use `prepare_agent_translations.py init` to create an auditable JSONL handoff from context packets. The Agent edits `target` only, then the validator checks chunk coverage, stable block IDs, nonempty targets, and protected-token preservation. Pass the validated file to `run_translation.py --translation-backend current-agent` only after `select_translation_backend.py` reports PDF reinjection support.

## Partial pages and cache

Use page selection for diagnosis and retry. Keep `only_include_translated_page` behavior in mind when merging partial outputs. Never splice PDF pages blindly when outlines, annotations, page labels, forms, or internal links matter; verify the merged artifact.

Keep cache enabled for layout-only retries. Bypass cache only for known bad translations and only for the smallest affected page range.

## Engine caveats

Known limitations can change by release. Treat lines, drop caps, large pages, scanned documents, author/reference parsing, table handling, and cross-page paragraphs as high-risk surfaces. Preflight and visual QA are mandatory when these occur.
