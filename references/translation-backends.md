# Translation backend selection

Keep the user-facing choice separate from the PDF engineering layer. PDFMathTranslate-next/BabelDOC remains responsible for parsing, layout, and PDF output; the options below decide who produces the translated text.

## Required menu order

Offer these choices in this order:

1. **Google 翻译（默认）** — fast, no separate API key, and supported as the PDFMathTranslate-next default. It requires network access and sends document text to Google.
2. **当前 Agent 大模型** — the Agent translates with the model already running this Skill, using the Document Profile, chapter/sliding context, glossary, Translation Memory, and protected-token rules. It does not ask the user to choose or configure another model provider.
3. **已配置的第三方或本地服务** — show provider-specific choices only when the user selects this item or already named a provider.

Do not ask the user to choose between PDFMathTranslate-next and BabelDOC. Those are implementation components, not translation choices.

If the user gives no preference, propose Google first and obtain permission before sending document content to an external service. Never silently switch providers after a failure.

## Current Agent mode

Current Agent mode is a two-stage path:

1. The Agent translates `current.text` from each context packet and writes stable-ID `agent-translations.jsonl`. It uses neighboring blocks only as read-only context.
2. A supported PDF-engine integration injects those translations into BabelDOC for typesetting.

Run `select_translation_backend.py --choice current-agent` before promising a layout-preserving PDF. If it reports `requires-agent-bridge`, the Agent can still produce and validate the translation bundle and editable Word text, but the installed engine cannot yet consume that bundle for PDF layout. Explain this limitation and let the user choose Google, a configured provider, or an explicitly installed/version-pinned bridge.

Do not claim that the current Agent is the same as an OpenAI API service. The Agent session does not automatically expose its active model as an API endpoint or API key.

## Agent translation contract

Initialize the bundle from `context-packets.jsonl`, fill only `target`, and validate it before reinjection. Preserve `chunk_id`, `block_ids`, numbers, URLs, identifiers, formula placeholders, and glossary-controlled terms. Store Agent output as draft until semantic and terminology QA pass.

Do not use private BabelDOC internals as a bridge unless the exact package version is pinned and covered by an end-to-end regression test. A missing bridge must stop PDF delivery rather than trigger an undeclared provider fallback.

## Configured service mode

Inspect the installed engine's help and show only services actually exposed there. Read credentials from environment variables or a private configuration file. Never put API keys in prompts, command previews, or manifests.
