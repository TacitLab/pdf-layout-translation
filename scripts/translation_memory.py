#!/usr/bin/env python3
"""Manage an auditable SQLite translation memory with exact and fuzzy lookup."""

from __future__ import annotations

import argparse
import json
import sqlite3
import unicodedata
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    return " ".join(text.casefold().split())


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


def initialize(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS units (
          id INTEGER PRIMARY KEY,
          source TEXT NOT NULL,
          source_normalized TEXT NOT NULL,
          target TEXT NOT NULL,
          source_lang TEXT NOT NULL,
          target_lang TEXT NOT NULL,
          status TEXT NOT NULL CHECK(status IN ('draft','approved','rejected')),
          project_id TEXT NOT NULL DEFAULT '',
          document_id TEXT NOT NULL DEFAULT '',
          chunk_id TEXT NOT NULL DEFAULT '',
          notes TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          UNIQUE(source_normalized, source_lang, target_lang, project_id, document_id)
        );
        CREATE INDEX IF NOT EXISTS idx_units_lookup
          ON units(source_lang, target_lang, status, project_id, document_id);
        """
    )
    connection.commit()


def add_unit(connection: sqlite3.Connection, args: argparse.Namespace) -> int:
    timestamp = now()
    values = {
        "source": args.source,
        "source_normalized": normalize(args.source),
        "target": args.target,
        "source_lang": args.source_lang,
        "target_lang": args.target_lang,
        "status": args.status,
        "project_id": args.project_id or "",
        "document_id": args.document_id or "",
        "chunk_id": args.chunk_id or "",
        "notes": args.notes or "",
        "created_at": timestamp,
        "updated_at": timestamp,
    }
    connection.execute(
        """
        INSERT INTO units (
          source, source_normalized, target, source_lang, target_lang, status,
          project_id, document_id, chunk_id, notes, created_at, updated_at
        ) VALUES (
          :source, :source_normalized, :target, :source_lang, :target_lang, :status,
          :project_id, :document_id, :chunk_id, :notes, :created_at, :updated_at
        )
        ON CONFLICT(source_normalized, source_lang, target_lang, project_id, document_id)
        DO UPDATE SET
          source = excluded.source,
          target = excluded.target,
          status = excluded.status,
          chunk_id = excluded.chunk_id,
          notes = excluded.notes,
          updated_at = excluded.updated_at
        """,
        values,
    )
    connection.commit()
    row = connection.execute(
        """SELECT id FROM units WHERE source_normalized=? AND source_lang=? AND
        target_lang=? AND project_id=? AND document_id=?""",
        (
            values["source_normalized"], values["source_lang"], values["target_lang"],
            values["project_id"], values["document_id"],
        ),
    ).fetchone()
    return int(row["id"])


def lookup(connection: sqlite3.Connection, args: argparse.Namespace) -> list[dict[str, Any]]:
    conditions = ["source_lang=?", "target_lang=?", "status!='rejected'"]
    values: list[Any] = [args.source_lang, args.target_lang]
    if args.project_id:
        conditions.append("project_id IN ('', ?)")
        values.append(args.project_id)
    if args.document_id:
        conditions.append("document_id IN ('', ?)")
        values.append(args.document_id)
    rows = connection.execute(
        f"SELECT * FROM units WHERE {' AND '.join(conditions)}", values
    ).fetchall()
    query = normalize(args.source)
    results = []
    for row in rows:
        score = SequenceMatcher(None, query, row["source_normalized"]).ratio()
        if score < args.threshold and query != row["source_normalized"]:
            continue
        item = dict(row)
        item["match"] = "exact" if query == row["source_normalized"] else "fuzzy"
        item["score"] = round(score, 6)
        item["auto_reuse_eligible"] = item["match"] == "exact" and row["status"] == "approved"
        results.append(item)
    results.sort(key=lambda item: (item["match"] != "exact", -item["score"], item["id"]))
    return results[: args.limit]


def export_units(connection: sqlite3.Connection, output: Path) -> int:
    rows = connection.execute("SELECT * FROM units ORDER BY id").fetchall()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(dict(row), ensure_ascii=False) + "\n")
    return len(rows)


def import_units(connection: sqlite3.Connection, input_path: Path) -> int:
    count = 0
    with input_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"Invalid JSONL at line {line_number}: {exc}") from exc
            namespace = argparse.Namespace(
                source=item["source"], target=item["target"],
                source_lang=item["source_lang"], target_lang=item["target_lang"],
                status=item.get("status", "draft"), project_id=item.get("project_id", ""),
                document_id=item.get("document_id", ""), chunk_id=item.get("chunk_id", ""),
                notes=item.get("notes", ""),
            )
            add_unit(connection, namespace)
            count += 1
    return count


def parser_for_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    init_parser = subparsers.add_parser("init")
    init_parser.add_argument("database")

    add_parser = subparsers.add_parser("add")
    add_parser.add_argument("database")
    add_parser.add_argument("--source", required=True)
    add_parser.add_argument("--target", required=True)
    add_parser.add_argument("--source-lang", required=True)
    add_parser.add_argument("--target-lang", required=True)
    add_parser.add_argument("--status", choices=("draft", "approved", "rejected"), default="draft")
    add_parser.add_argument("--project-id")
    add_parser.add_argument("--document-id")
    add_parser.add_argument("--chunk-id")
    add_parser.add_argument("--notes")

    lookup_parser = subparsers.add_parser("lookup")
    lookup_parser.add_argument("database")
    lookup_parser.add_argument("--source", required=True)
    lookup_parser.add_argument("--source-lang", required=True)
    lookup_parser.add_argument("--target-lang", required=True)
    lookup_parser.add_argument("--project-id")
    lookup_parser.add_argument("--document-id")
    lookup_parser.add_argument("--threshold", type=float, default=0.72)
    lookup_parser.add_argument("--limit", type=int, default=5)

    export_parser = subparsers.add_parser("export")
    export_parser.add_argument("database")
    export_parser.add_argument("--out", required=True)

    import_parser = subparsers.add_parser("import")
    import_parser.add_argument("database")
    import_parser.add_argument("--input", required=True)
    return parser


def main() -> int:
    args = parser_for_cli().parse_args()
    database = Path(args.database).expanduser().resolve()
    connection = connect(database)
    initialize(connection)
    if args.command == "init":
        print(json.dumps({"status": "initialized", "database": str(database)}, indent=2))
    elif args.command == "add":
        row_id = add_unit(connection, args)
        print(json.dumps({"status": "stored", "id": row_id}, indent=2))
    elif args.command == "lookup":
        if not 0 <= args.threshold <= 1:
            raise SystemExit("--threshold must be between 0 and 1")
        print(json.dumps(lookup(connection, args), ensure_ascii=False, indent=2))
    elif args.command == "export":
        output = Path(args.out).expanduser().resolve()
        print(json.dumps({"exported": export_units(connection, output), "out": str(output)}, indent=2))
    elif args.command == "import":
        input_path = Path(args.input).expanduser().resolve()
        if not input_path.is_file():
            raise SystemExit(f"Input not found: {input_path}")
        print(json.dumps({"imported": import_units(connection, input_path)}, indent=2))
    connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
