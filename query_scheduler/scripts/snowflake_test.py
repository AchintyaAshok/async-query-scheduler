#!/usr/bin/env python3
"""Test Snowflake connectivity, list tables, and run a sample read query.

Usage:
    uv run python scripts/snowflake_test.py status
    uv run python scripts/snowflake_test.py tables
    uv run python scripts/snowflake_test.py query "SELECT * FROM some_table LIMIT 5"
    uv run python scripts/snowflake_test.py --help
"""

import argparse
import os
import sys
from pathlib import Path


def find_project_root() -> Path:
    """Walk up from cwd to find project root, fall back to cwd."""
    if project_root := os.environ.get("PROJECT_ROOT"):
        return Path(project_root).resolve()
    candidate = Path.cwd()
    markers = {".git", "pyproject.toml", "package.json", "Cargo.toml", "go.mod"}
    while candidate != candidate.parent:
        if any((candidate / m).exists() for m in markers):
            return candidate
        candidate = candidate.parent
    return Path.cwd()


def _load_env() -> None:
    """Load .env file into os.environ if dotenv is not available."""
    env_path = find_project_root() / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def _connect():
    """Create a Snowflake connection using env vars."""
    import snowflake.connector

    return snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        password=os.environ["SNOWFLAKE_PASSWORD"],
        warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
        database=os.environ["SNOWFLAKE_DATABASE"],
        schema=os.environ.get("SNOWFLAKE_SCHEMA", "PUBLIC"),
    )


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------


def cmd_status(args: argparse.Namespace) -> None:
    """Test basic Snowflake connectivity."""
    print("Connecting to Snowflake...")
    try:
        conn = _connect()
        cursor = conn.cursor()
        cursor.execute("SELECT CURRENT_VERSION()")
        version = cursor.fetchone()[0]
        cursor.execute(
            "SELECT CURRENT_WAREHOUSE(), CURRENT_DATABASE(), CURRENT_SCHEMA()"
        )
        wh, db, schema = cursor.fetchone()
        print("  Connected successfully!")
        print(f"  Snowflake version: {version}")
        print(f"  Warehouse: {wh}")
        print(f"  Database:  {db}")
        print(f"  Schema:    {schema}")
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"  Connection FAILED: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_tables(args: argparse.Namespace) -> None:
    """List all tables in the current schema."""
    print("Listing tables...")
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute("SHOW TABLES")
    rows = cursor.fetchall()
    if not rows:
        print("  No tables found.")
    else:
        # SHOW TABLES columns: created_on, name, database_name, schema_name, ...
        print(f"  Found {len(rows)} table(s):\n")
        for row in rows:
            name = row[1]
            db = row[2]
            schema = row[3]
            row_count = row[5] if len(row) > 5 else "?"
            print(f"    {db}.{schema}.{name}  (rows: {row_count})")
    cursor.close()
    conn.close()


def cmd_query(args: argparse.Namespace) -> None:
    """Run an arbitrary read query and print results."""
    sql = args.sql
    print(f"Executing: {sql}\n")
    conn = _connect()
    cursor = conn.cursor(snowflake.connector.DictCursor)
    try:
        cursor.execute(sql)
        rows = cursor.fetchall()
        if not rows:
            print("  Query returned 0 rows.")
            return
        # Print column headers
        columns = list(rows[0].keys())
        print("  " + " | ".join(columns))
        print("  " + "-+-".join("-" * max(len(c), 10) for c in columns))
        for row in rows[: args.limit]:
            vals = [str(row.get(c, "")) for c in columns]
            print("  " + " | ".join(vals))
        if len(rows) > args.limit:
            print(f"\n  ... showing {args.limit} of {len(rows)} rows")
        else:
            print(f"\n  {len(rows)} row(s) returned.")
    except Exception as e:
        print(f"  Query FAILED: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        cursor.close()
        conn.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

# Lazy import for DictCursor used in cmd_query
import snowflake.connector  # noqa: E402


def main() -> None:
    _load_env()

    parser = argparse.ArgumentParser(
        description="Test Snowflake connectivity, list tables, and run queries",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="Test connection and show Snowflake info")
    sub.add_parser("tables", help="List tables in the current schema")

    query_p = sub.add_parser("query", help="Run a read query")
    query_p.add_argument("sql", help="SQL query to execute")
    query_p.add_argument(
        "--limit", type=int, default=20, help="Max rows to display (default: 20)"
    )

    args = parser.parse_args()
    commands = {
        "status": cmd_status,
        "tables": cmd_tables,
        "query": cmd_query,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
