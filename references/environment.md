# Environment setup

## Principle

Detect first, propose second, install only with approval. Environment inspection must not mutate the machine or access the network.

## Supported paths

Prefer an existing `pdf2zh_next` executable. If it is absent, prefer an isolated `uv tool` install on macOS or an official container on Linux. Avoid adding the engine and its heavy dependencies to the user's active project environment.

Run the read-only check:

```bash
python scripts/doctor.py --json
```

Preview the install command:

```bash
python scripts/setup_environment.py
```

After the user approves installation and network access:

```bash
python scripts/setup_environment.py --apply
```

The installer intentionally does not warm up assets. After installation, preview the installed CLI help and run its supported `--warmup` form with explicit approval; model and font assets can be large and require network access.

## Python dependencies

The inspection, extraction, TOC reconstruction, rendering, semantic QA, and terminology QA scripts require PyMuPDF (`fitz`). Editable Word export and correction import require `python-docx`. Scripts fail with a direct installation hint when either dependency is unavailable. Translation-memory and manifest scripts use only the Python standard library.

Use an isolated environment when dependencies are missing:

```bash
python -m pip install PyMuPDF python-docx
```

TOC reconstruction also needs an installed font that covers the target language. For Chinese output, prefer PingFang, Songti, Microsoft YaHei, or Noto Sans CJK and pass an explicit font path when automatic discovery is insufficient.

## Secrets

Use provider environment variables or a private engine config file. Do not put API keys in:

- command history;
- `translation-run.json`;
- `profile-prompt.txt`;
- QA artifacts;
- the final ZIP.

`run_translation.py` rejects common API-key flags in passthrough arguments so that the run record remains safe to share.

## Translation-method readiness

Run `select_translation_backend.py` after environment inspection. Google is the first/default method and requires network access plus permission to transmit document text externally. The current Agent requires no separate provider selection, but PDF delivery still depends on a detected translation-reinjection bridge. If that bridge is absent, report the limitation instead of changing the method. Configured providers must use existing environment variables or private engine configuration.
