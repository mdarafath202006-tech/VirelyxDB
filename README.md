# VirelyxDB

VirelyxDB is a tiny relational storage-engine learning project written in Python. It provides table schemas, JSON-backed durable storage, insert/select/update/delete operations, equality indexes, and a write-ahead log (WAL) recovery path.

## Requirements
Python 3.10+. No third-party dependencies.

## Quick start
```bash
python virelyxdb.py create-table users id:int name:str city:str
python virelyxdb.py insert users '{"id":1,"name":"Asha","city":"Chennai"}'
python virelyxdb.py insert users '{"id":2,"name":"Ravi","city":"Madurai"}'
python virelyxdb.py select users
python virelyxdb.py select users --where city=Chennai
python -m unittest discover -s tests -v
```

The database lives in `.virelyxdb/database.json` and its WAL in `.virelyxdb/wal.jsonl`. Override the directory with `--data-dir PATH` on every command.

## Supported types
`int`, `str`, `float`, `bool`. All columns are required on insert; extra fields and mismatched types are rejected. Equality filters use an in-memory sorted index rebuilt from persisted rows.

## Recovery model
Before a state snapshot is persisted, VirelyxDB appends that snapshot to the WAL. On startup, any valid WAL snapshot newer than the database file is replayed. This illustrates the ordering and recovery idea behind WAL; it is not a production-grade page-level WAL, locking, or concurrent transaction system.

## Scope and limitations
This is a single-process educational MVP: JSON snapshots, no SQL parser, no joins, no concurrency control, no page cache, and no multi-user server. The CLI is a simple query interface over the storage engine.