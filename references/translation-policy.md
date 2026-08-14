# Translation policy

## Priority order

Resolve translation decisions in this order:

1. Explicit user instructions and user glossary.
2. Approved project glossary and approved translation memory.
3. Approved document-specific terms.
4. Engine-extracted term candidates.
5. Model judgment constrained by the Document Profile.

Never overwrite a higher-priority term with a lower-priority suggestion.

## Translate by default

Translate prose, headings, list items, footnotes, captions, ordinary annotations, semantic table-cell text, and meaningful headers/footers.

## Preserve by default

Preserve mathematical formulas, source code, shell commands, API identifiers, URLs, email addresses, DOI values, UUIDs, hashes, file paths, citation markers, product/model identifiers, numbers, and measurement units. Preserve trademarks and project names unless the user or glossary defines a localized form.

## Glossary CSV

Use UTF-8 CSV with these columns:

```csv
source,target,tgt_lng,notes
Control Plane,控制平面,zh-CN,approved
Pod,Pod,zh-CN,preserve
```

The engine may accept only `source`, `target`, and optional `tgt_lng`; extra columns are for the agent and QA scripts. Create an engine-facing copy if the installed release rejects extra columns.

Reject or manually resolve:

- duplicate sources with conflicting targets;
- empty source or target fields;
- case-only duplicates with different decisions;
- entries that change protected tokens unintentionally.

## Style and ambiguity

Record document-level decisions in `profile.json`: domain, audience, register, locale, punctuation, capitalization, number formatting, abbreviation expansion, and whether common technical nouns remain in English.

Mark uncertain terms as candidates. Ask for confirmation only when the choice is consequential across the document; otherwise select a consistent provisional form and expose it in the final glossary.

## Images and tables

Do not translate text baked into raster images by default. OCR, removal, and redraw are separate operations with separate visual QA.

For tables, preserve row/column geometry, numeric alignment, units, footnote markers, and reading order. Prefer leaving a difficult cell untranslated over corrupting the table structure, and record the exception.

## TOC and index pages

Translate TOC headings and row titles only. Preserve section numbers, destination labels, internal links, row order, and row coordinates. Regenerate dot leaders from geometry instead of translating or copying them as prose.

Protect product identifiers and mixed-case tokens inside titles. For example, `FLSTDmSCHE`, `SmartKey`, and `4pCO Manager` remain unchanged unless an approved glossary says otherwise. A heading such as `INDEX` may become `目录`, but the page must remain a row-addressable navigation structure rather than a paragraph.
