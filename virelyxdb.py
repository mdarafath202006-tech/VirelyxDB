#!/usr/bin/env python3
"""VirelyxDB: a small JSON-backed relational storage engine."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from typing import Any

SUPPORTED_TYPES = {"int", "str", "float", "bool"}

class VirelyxDB:
    def __init__(self, data_dir: str | Path = ".virelyxdb"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "database.json"
        self.wal_path = self.data_dir / "wal.jsonl"
        self.state: dict[str, Any] = {"version": 1, "tables": {}}
        if self.db_path.exists():
            self.state = json.loads(self.db_path.read_text(encoding="utf-8"))
        self._recover()
        self._rebuild_indexes()

    def _recover(self) -> None:
        if not self.wal_path.exists():
            return
        lines = self.wal_path.read_text(encoding="utf-8").splitlines()
        latest = None
        for line in lines:
            try:
                record = json.loads(line)
                if record.get("kind") == "snapshot" and isinstance(record.get("state"), dict):
                    latest = record["state"]
            except json.JSONDecodeError:
                # A truncated final WAL record is ignored.
                continue
        if latest is not None:
            self.state = latest
            self._persist()
        self.wal_path.write_text("", encoding="utf-8")

    def _persist(self) -> None:
        self.db_path.write_text(json.dumps(self.state, indent=2, sort_keys=True), encoding="utf-8")

    def _commit(self) -> None:
        record = json.dumps({"kind": "snapshot", "state": self.state}, separators=(",", ":"))
        with self.wal_path.open("a", encoding="utf-8") as wal:
            wal.write(record + "\n")
            wal.flush()
        self._persist()
        self.wal_path.write_text("", encoding="utf-8")
        self._rebuild_indexes()

    def _rebuild_indexes(self) -> None:
        self.indexes: dict[str, dict[str, dict[str, list[int]]]] = {}
        for name, table in self.state["tables"].items():
            self.indexes[name] = {}
            for column in table["columns"]:
                values: dict[str, list[int]] = {}
                for i, row in enumerate(table["rows"]):
                    key = json.dumps(row[column], sort_keys=True)
                    values.setdefault(key, []).append(i)
                self.indexes[name][column] = values

    def create_table(self, name: str, columns: dict[str, str]) -> None:
        if not name or name in self.state["tables"]:
            raise ValueError(f"table already exists or invalid: {name}")
        if not columns:
            raise ValueError("at least one column is required")
        for column, kind in columns.items():
            if not column.isidentifier() or kind not in SUPPORTED_TYPES:
                raise ValueError(f"invalid column/type: {column}:{kind}")
        self.state["tables"][name] = {"columns": columns, "rows": []}
        self._commit()

    def _table(self, name: str) -> dict:
        try:
            return self.state["tables"][name]
        except KeyError as exc:
            raise ValueError(f"unknown table: {name}") from exc

    @staticmethod
    def _valid_type(value: Any, kind: str) -> bool:
        # bool is a subclass of int in Python; treat it separately.
        if kind == "int": return isinstance(value, int) and not isinstance(value, bool)
        if kind == "str": return isinstance(value, str)
        if kind == "float": return isinstance(value, (int, float)) and not isinstance(value, bool)
        if kind == "bool": return isinstance(value, bool)
        return False

    def insert(self, table_name: str, row: dict[str, Any]) -> dict:
        table = self._table(table_name)
        columns = table["columns"]
        if set(row) != set(columns):
            raise ValueError(f"row fields must exactly match schema: {list(columns)}")
        for column, kind in columns.items():
            if not self._valid_type(row[column], kind):
                raise ValueError(f"{column} must be {kind}")
        table["rows"].append(dict(row))
        self._commit()
        return dict(row)

    def select(self, table_name: str, where: tuple[str, Any] | None = None) -> list[dict]:
        table = self._table(table_name)
        rows = table["rows"]
        if where is None:
            return [dict(row) for row in rows]
        column, value = where
        if column not in table["columns"]:
            raise ValueError(f"unknown column: {column}")
        # Equality index maps serialized values to row offsets.
        key = json.dumps(value, sort_keys=True)
        offsets = self.indexes[table_name][column].get(key, [])
        return [dict(rows[i]) for i in offsets if rows[i].get(column) == value]

    def update(self, table_name: str, where: tuple[str, Any], changes: dict[str, Any]) -> int:
        table = self._table(table_name)
        column, value = where
        if column not in table["columns"] or not changes or not set(changes).issubset(table["columns"]):
            raise ValueError("invalid filter or update columns")
        for field, new_value in changes.items():
            if not self._valid_type(new_value, table["columns"][field]):
                raise ValueError(f"{field} must be {table['columns'][field]}")
        changed = 0
        for row in table["rows"]:
            if row.get(column) == value:
                row.update(changes)
                changed += 1
        if changed:
            self._commit()
        return changed

    def delete(self, table_name: str, where: tuple[str, Any]) -> int:
        table = self._table(table_name)
        column, value = where
        if column not in table["columns"]:
            raise ValueError(f"unknown column: {column}")
        before = len(table["rows"])
        table["rows"] = [row for row in table["rows"] if row.get(column) != value]
        removed = before - len(table["rows"])
        if removed:
            self._commit()
        return removed

def parse_value(raw: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="VirelyxDB educational relational store")
    parser.add_argument("--data-dir", default=".virelyxdb", help="database directory")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("create-table"); p.add_argument("table"); p.add_argument("columns", nargs="+", help="name:type")
    p = sub.add_parser("insert"); p.add_argument("table"); p.add_argument("json_row")
    p = sub.add_parser("select"); p.add_argument("table"); p.add_argument("--where", help="column=value")
    p = sub.add_parser("update"); p.add_argument("table"); p.add_argument("--where", required=True); p.add_argument("--set", required=True, dest="changes")
    p = sub.add_parser("delete"); p.add_argument("table"); p.add_argument("--where", required=True)
    args = parser.parse_args(argv)
    db = VirelyxDB(args.data_dir)
    if args.command == "create-table":
        columns = {}
        for item in args.columns:
            if ":" not in item: parser.error("columns must use name:type")
            name, kind = item.split(":", 1); columns[name] = kind
        db.create_table(args.table, columns); print(f"created table {args.table}")
    elif args.command == "insert":
        row = json.loads(args.json_row); print(json.dumps(db.insert(args.table, row), indent=2))
    elif args.command == "select":
        where = None
        if args.where:
            if "=" not in args.where: parser.error("--where must be column=value")
            col, val = args.where.split("=", 1); where = (col, parse_value(val))
        print(json.dumps(db.select(args.table, where), indent=2))
    elif args.command == "update":
        col, val = args.where.split("=", 1); changes = json.loads(args.changes)
        print(f"updated {db.update(args.table, (col, parse_value(val)), changes)} row(s)")
    elif args.command == "delete":
        col, val = args.where.split("=", 1)
        print(f"deleted {db.delete(args.table, (col, parse_value(val)))} row(s)")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
