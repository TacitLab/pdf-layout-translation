# Artifact schemas

All JSON artifacts use UTF-8, one-based page numbers, stable kebab-case finding codes, and `schema_version: "0.4"`.

## Translation backend selection

Required keys: `schema_version`, `tool`, `generated_at`, `engine`, `options`, `selected`, `status`, and `policy`. Options are ordered and use stable IDs `google`, `current-agent`, and `configured`. The policy must declare `default: google` and `do_not_silently_fallback: true`.

## Current-Agent translations JSONL

Each line requires `schema_version`, `provider`, `chunk_id`, `block_ids`, `source`, `target`, `protected_tokens`, and `status`. The Agent may populate `target`; IDs and source-side fields remain immutable. The validation report follows the QA report schema.

## Profile

Required top-level keys: `schema_version`, `document_id`, `source`, `languages`, `statistics`, `sections`, `style`, `term_candidates`, `protected_token_summary`, and `provenance`.

## Blocks JSONL

Each line contains `block_id`, `page`, `order`, `section_id`, `kind`, `bbox`, and `text`. Bounding boxes use PDF points in `[x0, y0, x1, y1]` order.

## Context packets JSONL

Each line contains `schema_version`, `chunk_id`, `section`, `previous`, `current`, `next`, and `profile`. `current.block_ids` uniquely identifies the translation unit.

## Translation run

Required keys: `schema_version`, `engine`, `engine_path`, `engine_help_fingerprint`, `translation_backend`, `translation_backend_details`, `context_mode`, `command`, `started_at`, `finished_at`, `returncode`, and `outputs`. Redact secrets; store commands as argument arrays, not shell strings.

## QA reports

Each report contains `schema_version`, `tool`, `summary`, and `findings`. A finding contains `severity`, `code`, `message`, and optional `page`, `evidence`, and `suggested_action`.

## QA manifest

Required keys: `schema_version`, `gate`, `inputs`, `coverage`, `summary`, `findings`, `waivers`, and `generated_at`. Keep source report provenance on every merged finding.

## Retry plan

Required keys: `schema_version`, `source_manifest`, `retry_groups`, and `manual_actions`. Each retry group contains `pages`, `reasons`, `recommended_options`, and a safe argument array. A plan is advisory until an agent verifies support with the installed engine's help.

## TOC extraction and translation

TOC extraction requires `schema_version`, `tool`, `source`, `page`, `heading`, `rows`, `metrics`, `detection_score`, and `source_link_count`. Every row requires stable `row_id`, `section_number`, `source_title`, `destination_label`, row/title/leader/destination geometry, source font metadata, protected tokens, and matching link rectangles. The companion translation-template file contains the same row IDs and the editable target fields.

The editable translation template preserves `row_id` and adds `target_title`. Renderers must reject missing row IDs or changed protected tokens.

## Editable Word manifest and corrections

The Word manifest requires `schema_version`, `tool`, `generated_at`, `source`, `output`, `style_preset`, `header_pattern`, and `items`. Each item contains a stable `item_id`, one-based `page`, `kind`, editable text, and optional PDF bounding box.

Correction export is JSONL. Each line contains `schema_version`, `item_id`, `corrected_text`, `source_docx`, and `extracted_at`. The hidden `[[ID:...]]` marker is authoritative; visible table position is not a stable identifier.
