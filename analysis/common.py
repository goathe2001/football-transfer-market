"""Shared helpers: database connection and column checks."""
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "transfermarkt.duckdb"
FIG_DIR = ROOT / "figures"
OUT_DIR = ROOT / "outputs"


def connect() -> duckdb.DuckDBPyConnection:
    if not DB_PATH.exists():
        raise SystemExit(f"Database not found at {DB_PATH}. Run data/download.sh first.")
    return duckdb.connect(str(DB_PATH), read_only=True)


def columns(con, table: str) -> set[str]:
    rows = con.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = ?", [table]
    ).fetchall()
    return {r[0] for r in rows}


def require(con, table: str, needed: set[str]) -> None:
    missing = needed - columns(con, table)
    if missing:
        raise SystemExit(
            f"Table '{table}' is missing columns {sorted(missing)}. "
            "Run analysis/00_inspect.py and adjust the SQL to the real schema."
        )
