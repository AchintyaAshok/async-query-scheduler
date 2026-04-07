#!/usr/bin/env python3
"""End-to-end smoke test for the query scheduler API.

Starts the API server, submits a query, validates sanitization middleware,
polls for status, and verifies result retrieval from Snowflake.

Usage:
    uv run python scripts/smoke_test.py run
    uv run python scripts/smoke_test.py run --no-start-server
    uv run python scripts/smoke_test.py --help
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
INFO = "\033[94mINFO\033[0m"

results: list[tuple[str, bool, str]] = []


def check(name: str, passed: bool, detail: str = "") -> bool:
    """Record a test result and print it."""
    status = PASS if passed else FAIL
    msg = f"  [{status}] {name}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    results.append((name, passed, detail))
    return passed


def api_request(
    url: str,
    method: str = "GET",
    data: dict | None = None,
) -> tuple[int, dict | str]:
    """Make an HTTP request and return (status_code, parsed_body)."""
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={"Content-Type": "application/json"} if body else {},
    )
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read().decode()
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, raw


def wait_for_server(base_url: str, timeout: int = 15) -> bool:
    """Wait for the server to be ready."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"{base_url}/health", timeout=2)
            return True
        except Exception:
            time.sleep(0.5)
    return False


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------


def test_health(base_url: str) -> None:
    """Test health endpoint."""
    print(f"\n{'=' * 60}")
    print("1. Health Check")
    print(f"{'=' * 60}")
    status, body = api_request(f"{base_url}/health")
    check("health endpoint returns 200", status == 200)
    check(
        "health status is ok",
        isinstance(body, dict) and body.get("status") == "ok",
    )


def test_sanitization(base_url: str) -> None:
    """Test SQL sanitization middleware rejects dangerous queries."""
    print(f"\n{'=' * 60}")
    print("2. Query Sanitization Middleware")
    print(f"{'=' * 60}")

    dangerous_queries = [
        ("DROP TABLE users", "blocks DDL (DROP TABLE)"),
        ("DELETE FROM users WHERE 1=1", "blocks DML (DELETE)"),
        ("INSERT INTO users VALUES (1)", "blocks DML (INSERT)"),
        ("CREATE TABLE evil (id int)", "blocks DDL (CREATE)"),
        ("SELECT 1; SELECT 2", "blocks multi-statement SQL"),
        ("GRANT ALL ON users TO public", "blocks DCL (GRANT)"),
    ]

    for sql, label in dangerous_queries:
        status, body = api_request(
            f"{base_url}/queries",
            method="POST",
            data={"sql": sql},
        )
        detail = ""
        if isinstance(body, dict):
            detail = body.get("detail", "")
        check(label, status == 422, f"status={status} {detail}")

    # Empty query
    status, body = api_request(
        f"{base_url}/queries",
        method="POST",
        data={"sql": ""},
    )
    check("blocks empty query", status == 422)

    # Valid SELECT should pass
    status, body = api_request(
        f"{base_url}/queries",
        method="POST",
        data={"sql": "SELECT 1 AS test"},
    )
    check("allows valid SELECT", status == 201, f"status={status}")


def test_query_lifecycle(base_url: str) -> None:
    """Test full query lifecycle: submit -> poll -> results."""
    print(f"\n{'=' * 60}")
    print("3. Query Lifecycle (submit -> poll -> results)")
    print(f"{'=' * 60}")

    sql = "SELECT * FROM USERS LIMIT 5"
    print(f"  [{INFO}] Submitting: {sql}")
    status, body = api_request(
        f"{base_url}/queries",
        method="POST",
        data={"sql": sql},
    )

    if not check("submit returns 201", status == 201, f"status={status}"):
        return

    query_id = body["id"]
    initial_status = body["status"]
    print(f"  [{INFO}] Query ID: {query_id}")
    print(f"  [{INFO}] Initial status: {initial_status}")

    check(
        "initial status is PENDING or RUNNING",
        initial_status in ("PENDING", "RUNNING"),
        f"got {initial_status}",
    )

    # Poll until complete or timeout
    print(f"\n  [{INFO}] Polling for completion (max 30s)...")
    deadline = time.time() + 30
    final_body = None
    poll_count = 0

    while time.time() < deadline:
        poll_count += 1
        status, body = api_request(f"{base_url}/queries/{query_id}")

        if not isinstance(body, dict):
            time.sleep(2)
            continue

        current_status = body.get("status", "UNKNOWN")
        print(f"  [{INFO}] Poll #{poll_count}: status={current_status}")

        if current_status in ("SUCCESS", "FAILED"):
            final_body = body
            break

        time.sleep(2)

    if final_body is None:
        check("query completed within timeout", False, "timed out after 30s")
        return

    check(
        "query completed with SUCCESS",
        final_body["status"] == "SUCCESS",
        f"got {final_body['status']}",
    )

    check(
        "result has row_count",
        final_body.get("row_count") is not None and final_body["row_count"] > 0,
        f"row_count={final_body.get('row_count')}",
    )

    rows = final_body.get("result_rows", [])
    check(
        "result has result_rows",
        isinstance(rows, list) and len(rows) > 0,
        f"rows={len(rows)}",
    )

    if rows:
        first_row = rows[0]
        print(f"  [{INFO}] Sample row: {json.dumps(first_row, indent=2)}")
        check(
            "result rows have expected columns",
            "USER_ID" in first_row and "REGION" in first_row,
            f"columns={list(first_row.keys())}",
        )

    check(
        "snowflake_query_id is populated",
        bool(final_body.get("snowflake_query_id")),
    )


def test_not_found(base_url: str) -> None:
    """Test 404 for unknown query ID."""
    print(f"\n{'=' * 60}")
    print("4. Error Handling")
    print(f"{'=' * 60}")
    fake_id = "00000000-0000-0000-0000-000000000000"
    status, _ = api_request(f"{base_url}/queries/{fake_id}")
    check("unknown query returns 404", status == 404)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def cmd_run(args: argparse.Namespace) -> None:
    """Run the full smoke test suite."""
    base_url = args.base_url.rstrip("/")
    server_proc = None

    if args.start_server:
        print(f"[{INFO}] Starting API server on port {args.port}...")
        root = find_project_root()
        server_proc = subprocess.Popen(
            [
                "uv",
                "run",
                "uvicorn",
                "query_scheduler.app:app",
                "--host",
                "0.0.0.0",
                "--port",
                str(args.port),
            ],
            cwd=root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        base_url = f"http://localhost:{args.port}"

        if not wait_for_server(base_url):
            print(f"  [{FAIL}] Server failed to start within 15s")
            server_proc.kill()
            sys.exit(1)
        print(f"  [{PASS}] Server ready at {base_url}")

    try:
        test_health(base_url)
        test_sanitization(base_url)
        test_query_lifecycle(base_url)
        test_not_found(base_url)
    finally:
        if server_proc:
            print(f"\n[{INFO}] Stopping server...")
            server_proc.send_signal(signal.SIGTERM)
            server_proc.wait(timeout=5)

    # Summary
    passed = sum(1 for _, ok, _ in results if ok)
    failed = sum(1 for _, ok, _ in results if not ok)
    total = len(results)

    print(f"\n{'=' * 60}")
    print(f"SUMMARY: {passed}/{total} passed, {failed} failed")
    print(f"{'=' * 60}")

    if failed > 0:
        print("\nFailed tests:")
        for name, ok, detail in results:
            if not ok:
                print(f"  - {name}: {detail}")
        sys.exit(1)
    else:
        print("\nAll tests passed!")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="End-to-end smoke test for the query scheduler API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="Run the full smoke test suite")
    run_p.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="API base URL (default: http://localhost:8000)",
    )
    run_p.add_argument(
        "--start-server",
        action="store_true",
        default=True,
        help="Auto-start the API server (default: true)",
    )
    run_p.add_argument(
        "--no-start-server",
        action="store_false",
        dest="start_server",
        help="Assume server is already running",
    )
    run_p.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Port for auto-started server (default: 8765)",
    )

    args = parser.parse_args()
    commands = {"run": cmd_run}
    commands[args.command](args)


if __name__ == "__main__":
    main()
