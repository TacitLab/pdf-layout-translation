# Environment setup

## Principle

Detect first, propose second, install only with approval. Environment inspection must not mutate the machine or access the network. Everything is one-time per machine: the engine install is global, and model/font downloads land in a persistent cache. Re-installing or re-downloading on every task is a process bug, not a requirement.

## Readiness verdict

`doctor.py` is the single source of truth. Its `summary.verdict` is one of:

- `ready` — engine and Python dependencies present. Skip all installation and warmup.
- `needs-python-deps` — only `PyMuPDF`/`python-docx` are missing. Install exactly those, nothing else.
- `needs-engine` — the PDF engine is absent. One `setup_environment.py --apply` run fixes it.

The report also includes `warmup_assets` (BabelDOC layout model and fonts under `~/.cache/babeldoc`, roughly 300+ MB) and `uv_tools.executable_conflict` (legacy `pdf2zh` 1.x and `pdf2zh-next` both ship a `pdf2zh` executable). Persist the report with `--json-out` into the run directory and re-read it after context compression instead of probing again.

## Supported paths

Prefer an existing `pdf2zh_next` executable. If it is absent, prefer an isolated `uv tool` install on macOS or an official container on Linux. Avoid adding the engine and its heavy dependencies to the user's active project environment.

Run the read-only check:

```bash
python scripts/doctor.py --json --json-out work/<id>/doctor.json
```

Preview the install command:

```bash
python scripts/setup_environment.py
```

After the user approves installation and network access:

```bash
python scripts/setup_environment.py --apply
```

If a leftover pdf2zh 1.x tool makes `uv tool install` abort with an executable conflict, the installer retries once with `--force` automatically; report that this happened.

The installer intentionally does not warm up assets. When `doctor.py` reports `warmup_assets.ready: true`, skip warmup. Otherwise, preview the installed CLI help and run its supported `--warmup` form with explicit approval; model and font assets are large, download once per machine into `~/.cache/babeldoc`, and require network access. If HuggingFace is unreachable or slow, set `HF_ENDPOINT=https://hf-mirror.com` before warmup; if PyPI is slow, set `UV_DEFAULT_INDEX` to a nearby mirror.

## Engine defaults

The installed engine's default translation service may not be Google (some releases default to a SiliconFlow free tier). `run_translation.py` passes an explicit `--google` when the user chose Google, so always go through it rather than invoking the engine by hand.

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
