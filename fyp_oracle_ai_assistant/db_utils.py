import os
import json
import sqlite3
from dotenv import load_dotenv
from typing import Dict, List, Tuple

load_dotenv()

# Guardrails
MAX_ROWS = int(os.getenv("MAX_ROWS", "500"))
SAFE_MODE = os.getenv("SAFE_MODE", "true").lower() == "true"

# DB aliases + paths
DB1_ALIAS = os.getenv("SQLITE_DB1_ALIAS", "FYP")
DB2_ALIAS = os.getenv("SQLITE_DB2_ALIAS", "HR")

DB_CONFIGS = {
    DB1_ALIAS: {"path": os.getenv("SQLITE_DB1_PATH")},
    DB2_ALIAS: {"path": os.getenv("SQLITE_DB2_PATH")},
}

# Active DB (changes via dropdown)
CURRENT_DB = list(DB_CONFIGS.keys())[0]


def set_active_db(alias: str):
    """Switch active SQLite DB (called from frontend dropdown)."""
    global CURRENT_DB
    if alias not in DB_CONFIGS:
        raise ValueError(f"❌ Unknown DB alias: {alias}")
    CURRENT_DB = alias


def get_db_path() -> str:
    """Return filesystem path for current DB."""
    path = DB_CONFIGS[CURRENT_DB].get("path")
    if not path:
        raise ValueError(f"❌ Missing SQLite path for {CURRENT_DB}. Check .env SQLITE_DB*_PATH")
    if not os.path.exists(path):
        raise FileNotFoundError(f"❌ SQLite DB not found: {path}")
    return path


def get_connection() -> sqlite3.Connection:
    """Create SQLite connection for the currently selected DB."""
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def fetch_schema(force: bool = False) -> Dict[str, List[str]]:
    """Read schema (tables + columns) for SQLite and cache it (per DB)."""
    cache_file = f"schema_cache_{CURRENT_DB}.json"

    if (not force) and os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass  # rebuild if cache corrupt

    schema: Dict[str, List[str]] = {}

    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT name
            FROM sqlite_master
            WHERE type='table'
              AND name NOT LIKE 'sqlite_%'
            ORDER BY name
        """)
        tables = [r[0] for r in cur.fetchall()]

        for t in tables:
            cur.execute(f'PRAGMA table_info("{t}")')
            cols = [row[1] for row in cur.fetchall()]  # (cid, name, type, notnull, dflt_value, pk)
            schema[t.upper()] = [c.upper() for c in cols]

    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(schema, f, indent=2)

    return schema


def schema_to_text(schema: Dict[str, List[str]], limit_tables: int = 40, limit_cols: int = 60) -> str:
    """Render a compact text representation of the schema for LLM prompts."""
    lines = []
    for i, (t, cols) in enumerate(schema.items()):
        if i >= limit_tables:
            lines.append(f"... ({len(schema) - limit_tables} more tables omitted)")
            break
        shown = cols[:limit_cols]
        extra = "" if len(cols) <= limit_cols else f", ... (+{len(cols) - limit_cols})"
        lines.append(f"{t}({', '.join(shown)}{extra})")
    return "\n".join(lines)


def is_safe_select(sql: str) -> bool:
    """In SAFE_MODE, allow only SELECT/WITH statements."""
    s = (sql or "").lstrip().upper()
    return s.startswith("SELECT") or s.startswith("WITH")


def run_sql(sql: str) -> Tuple[list, list]:
    """
    Execute SQL (read-only by default).
    Returns: (rows, colnames)
    """
    if SAFE_MODE and not is_safe_select(sql):
        raise RuntimeError("Unsafe SQL blocked. Only SELECT/WITH allowed (SAFE_MODE=true).")

    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(sql)

        colnames = [d[0] for d in cur.description] if cur.description else []
        rows = cur.fetchmany(MAX_ROWS)

    return [tuple(r) for r in rows], colnames


def list_nonempty_tables() -> list:
    """
    Return list of non-empty tables with their row count and columns.
    Format: [(TABLE_NAME, row_count, [COL1, COL2, ...]), ...]
    """
    results = []

    with get_connection() as conn:
        cur = conn.cursor()

        cur.execute("""
            SELECT name
            FROM sqlite_master
            WHERE type='table'
              AND name NOT LIKE 'sqlite_%'
            ORDER BY name
        """)
        tables = [r[0] for r in cur.fetchall()]

        for t in tables:
            try:
                cur.execute(f'SELECT COUNT(*) FROM "{t}"')
                count = cur.fetchone()[0] or 0
                if count > 0:
                    cur.execute(f'PRAGMA table_info("{t}")')
                    cols = [row[1] for row in cur.fetchall()]
                    results.append((t.upper(), int(count), [c.upper() for c in cols]))
            except Exception:
                pass

    return results