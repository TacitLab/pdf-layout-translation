# Document context and Translation Memory

## Document Profile

The deterministic profile builder extracts page statistics, likely headings, section boundaries, abbreviation candidates, protected-token examples, and term candidates. The agent or language model may enrich the profile, but must preserve provenance and confidence.

Keep the profile prompt concise. It is global guidance, not a full-document transcript.

## Context packet

Each JSONL record has one `current` unit plus read-only context:

```json
{
  "chunk_id": "sec-0002-chunk-0007",
  "section": {"id": "sec-0002", "title": "Methods"},
  "previous": [{"block_id": "p0003-b0012", "text": "..."}],
  "current": {"block_ids": ["p0003-b0013"], "text": "..."},
  "next": [{"block_id": "p0003-b0014", "text": "..."}],
  "profile": {"source_lang": "en", "target_lang": "zh-CN"}
}
```

Translate `current.text` only. Use previous and next text to resolve pronouns, ellipsis, terminology, figure/table references, and discourse continuity. Never echo or translate the context blocks into the returned output.

When the user selects the current Agent, initialize `agent-translations.jsonl` from these packets. Preserve `chunk_id`, `block_ids`, `source`, and `protected_tokens`; populate only `target`. Validate the completed handoff before reinjection. This makes the Agent path auditable and prevents neighboring context from leaking into the translated PDF.

## Chunking rules

- Keep a paragraph intact when possible.
- Do not cross a confident section boundary in a current chunk.
- Keep captions and their figure/table references together when extracted as adjacent blocks.
- Use stable block and chunk IDs so reruns address the same units.
- Carry two neighboring blocks by default; lower this for dense text and raise it only when the model context budget permits.

## Translation Memory commands

Initialize:

```bash
python scripts/translation_memory.py init tm.sqlite3
```

Add an accepted pair:

```bash
python scripts/translation_memory.py add tm.sqlite3 \
  --source "Control plane reconciles desired state." \
  --target "控制平面会协调期望状态。" \
  --source-lang en --target-lang zh-CN \
  --status approved --document-id guide-v2
```

Query exact and fuzzy candidates:

```bash
python scripts/translation_memory.py lookup tm.sqlite3 \
  --source "The control plane reconciles desired state." \
  --source-lang en --target-lang zh-CN --limit 5
```

Export auditable JSONL:

```bash
python scripts/translation_memory.py export tm.sqlite3 --out tm.jsonl
```

## Acceptance policy

- Reuse an exact, approved match automatically only when source/target languages and protection rules match.
- Present fuzzy matches as suggestions. Do not auto-apply them to numbers, negation, conditions, comparative statements, or legal/safety language.
- Store machine output as `draft`; promote to `approved` after terminology and semantic QA.
- Scope project-specific wording with `project_id` or `document_id`; avoid allowing one domain's memory to override another domain's glossary.
- Never store secrets or private provider prompts in the TM.
