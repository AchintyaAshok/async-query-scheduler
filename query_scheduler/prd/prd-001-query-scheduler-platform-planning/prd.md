# PRD 001: Query Scheduler Platform Planning

## Overview

A lightweight query scheduling platform that lets users submit SQL queries against customer-owned Snowflake warehouses, track their execution asynchronously, and retrieve results. Queries can take hours and must survive server crashes — state is persisted in Postgres and reconciled on restart via Snowflake's async query API.

This is a **planning PRD** — it defines the system architecture, schema design, API surface, and module boundaries. Implementation details will be broken into sub-PRDs per feature area.

### Context

Datadog integrates with customer data platforms that expose SQL interfaces with async result delivery. This system provides a generic query client abstraction starting with Snowflake, designed to extend to other warehouses.

### Existing Foundation

The project already has:
- **FastAPI + SQLModel + Alembic** stack with async Postgres
- **Repository pattern** (`AbstractRepository` → `SQLModelRepository`) in `core/storage/`
- **Pydantic Settings** in `core/config.py`
- **Health routes**, structured logging, optional OTel
- **Docker + docker-compose** with Postgres

## Linked Tickets

| Ticket | Title | Status |
|--------|-------|--------|
| - | Datadog Engineering Challenge | Active |

## Measures of Success

- [ ] `start_query(sql)` submits a query to Snowflake and returns a query ID within 2s
- [ ] `get_query_status(query_id)` returns accurate status mapped to `PENDING | RUNNING | SUCCESS | FAILED`
- [ ] Completed queries return result rows
- [ ] Query state survives server restart — pending/running queries are recovered on startup
- [ ] Malicious or dangerous SQL is rejected before reaching Snowflake
- [ ] All query operations are persisted in Postgres with full audit trail
- [ ] Integration tests pass against the live Snowflake instance

---

## System Architecture

### Module Map

```
src/query_scheduler/
├── core/
│   ├── config.py              # + Snowflake settings, feature flags, access scopes
│   ├── database.py            # Existing async engine
│   ├── storage/               # Existing repository pattern
│   │   ├── repository.py      # AbstractRepository (unchanged)
│   │   └── sql_repository.py  # SQLModelRepository (unchanged)
│   └── warehouse/             # NEW — warehouse abstraction layer
│       ├── __init__.py
│       ├── base.py            # AbstractWarehouse interface
│       └── snowflake.py       # Snowflake implementation (async query submit/poll)
├── models.py                  # + QueryRecord table
├── schemas.py                 # + Query request/response schemas
├── middleware/                 # NEW
│   ├── __init__.py
│   ├── query_sanitization.py  # SQL validation & sanitization
│   └── access_control.py      # Env-var-based capability gating
├── services/                  # NEW
│   ├── __init__.py
│   └── query_service.py       # Orchestration: submit, poll, recover
├── routes/
│   ├── health.py              # Existing
│   └── queries.py             # NEW — query API endpoints
└── app.py                     # + recovery on startup, middleware wiring
```

### Data Flow

```
User Request
    │
    ▼
[Access Control Middleware] ── check env-var scopes ── reject if unauthorized
    │
    ▼
[Query Sanitization Middleware] ── validate SQL ── reject if dangerous
    │
    ▼
[POST /queries] ── routes/queries.py
    │
    ▼
[QueryService.start_query()]
    ├── Persist QueryRecord (status=PENDING) → Postgres via repository
    ├── Submit async query → Snowflake via warehouse layer
    ├── Update QueryRecord (status=RUNNING, snowflake_query_id=...) → Postgres
    └── Return query_id to caller
    
[GET /queries/{id}/status]
    │
    ▼
[QueryService.get_query_status()]
    ├── Read QueryRecord from Postgres
    ├── If RUNNING → poll Snowflake for current status
    ├── If completed → fetch results, update record
    └── Return { status, results? }
    
[Startup Recovery]
    │
    ▼
[QueryService.recover_pending_queries()]
    ├── SELECT * FROM queries WHERE status IN (PENDING, RUNNING)
    ├── For PENDING → re-submit to Snowflake
    ├── For RUNNING → poll Snowflake to reconcile status
    └── Update records accordingly
```

---

## Schema Design

### QueryRecord Table

```python
class QueryStatus(str, Enum):
    PENDING = "PENDING"      # Persisted, not yet submitted to Snowflake
    RUNNING = "RUNNING"      # Submitted to Snowflake, awaiting completion
    SUCCESS = "SUCCESS"      # Snowflake returned results
    FAILED = "FAILED"        # Snowflake error or sanitization failure

class QueryRecord(SQLModel, table=True):
    __tablename__ = "queries"

    id: uuid.UUID            # Primary key, also our external query_id
    sql: str                 # Original SQL submitted by user
    status: QueryStatus      # Current lifecycle status
    snowflake_query_id: str | None  # Snowflake's async query handle
    result_rows: dict | None # JSON — result payload on SUCCESS
    error_message: str | None# Error details on FAILED
    row_count: int | None    # Number of result rows
    submitted_by: str | None # Caller identity (for future RBAC)
    created_at: datetime     # When the request was received
    updated_at: datetime     # Last status change
    started_at: datetime | None  # When Snowflake began execution
    completed_at: datetime | None # When final status was reached
```

**Design decisions:**
- UUID primary key — externally safe, no sequential ID leaking
- `result_rows` as JSON column — avoids a separate results table for Phase 1; can migrate to object storage later for large result sets
- `snowflake_query_id` nullable — filled after successful submission, null if we crash between persist and submit
- Timestamps for full audit trail and SLA tracking

---

## API Surface

### Core Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/queries` | Submit a new SQL query |
| `GET` | `/queries/{query_id}` | Get status + results |
| `GET` | `/queries` | List queries (paginated) |
| `GET` | `/health` | Existing liveness check |
| `GET` | `/ready` | Existing readiness check |

### Request/Response Schemas

```python
# POST /queries
class QueryCreate(BaseModel):
    sql: str

class QueryResponse(BaseModel):
    id: uuid.UUID
    status: QueryStatus
    sql: str
    created_at: datetime
    updated_at: datetime
    snowflake_query_id: str | None
    error_message: str | None
    row_count: int | None

class QueryResultResponse(QueryResponse):
    result_rows: list[dict] | None  # Only populated on SUCCESS
```

---

## Key Modules

### 1. Warehouse Abstraction (`core/warehouse/`)

```python
class AbstractWarehouse(ABC):
    async def submit_query(self, sql: str) -> str:
        """Submit SQL, return warehouse-native query ID."""
        
    async def get_query_status(self, query_id: str) -> WarehouseQueryStatus:
        """Poll for current status."""
        
    async def get_query_results(self, query_id: str) -> list[dict]:
        """Fetch result rows for a completed query."""
```

Snowflake implementation uses `snowflake-connector-python` with `_no_results=True` for async submission, then polls via `get_results_from_sfqid()`.

**Why a separate abstraction from the existing repository?** The repository pattern handles Postgres CRUD. The warehouse layer handles external data platform communication — different concern, different interface, different failure modes.

### 2. Query Sanitization (`middleware/query_sanitization.py`)

Middleware that intercepts `POST /queries` and validates SQL before it reaches the service layer.

**Phase 1 checks:**
- Block DDL statements (`CREATE`, `ALTER`, `DROP`, `TRUNCATE`)
- Block DCL statements (`GRANT`, `REVOKE`)
- Block dangerous operations (`DELETE`, `UPDATE`, `INSERT` — read-only queries only)
- Reject multiple statements (no semicolon-separated batches)
- Basic length limits
- Reject common injection patterns

**Not in Phase 1:** AST-level SQL parsing, query cost estimation, row limit enforcement.

### 3. Access Control (`middleware/access_control.py`)

Env-var-based capability gating as a stepping stone to full RBAC.

```python
# config.py additions
class Settings(BaseSettings):
    # Access control
    query_access_enabled: bool = True           # Global kill switch
    allowed_capabilities: str = "start_query,get_status,get_results"
    # Maps to: Set[str] parsed on startup
```

Middleware checks the request path against the enabled capabilities. This is intentionally simple — designed to be replaced by token-scoped RBAC later without changing the API contract.

### 4. Recovery Service (in `services/query_service.py`)

On application startup (in FastAPI lifespan):
1. Query Postgres for records with `status IN (PENDING, RUNNING)`
2. **PENDING** (never reached Snowflake): Re-submit to Snowflake, update record
3. **RUNNING** (submitted but no final status): Poll Snowflake by `snowflake_query_id` to get current status, reconcile

---

## Config Additions (`core/config.py`)

```python
class Settings(BaseSettings):
    # ... existing fields ...

    # Snowflake
    snowflake_account: str = ""
    snowflake_user: str = ""
    snowflake_password: str = ""
    snowflake_warehouse: str = ""
    snowflake_database: str = ""
    snowflake_schema: str = "PUBLIC"

    # Access Control
    query_access_enabled: bool = True
    allowed_capabilities: str = "start_query,get_status,get_results"

    # Query Limits
    max_query_length: int = 10000
    query_result_max_rows: int = 10000
```

---

## Testing Strategy

### Phase 1: Live Snowflake Integration Tests

```
tests/
├── conftest.py               # + Snowflake fixtures, test query helpers
├── test_health.py             # Existing
├── integration/
│   ├── test_snowflake.py      # Direct warehouse layer tests against live Snowflake
│   ├── test_query_api.py      # Full API flow: submit → poll → results
│   └── test_recovery.py       # Crash recovery simulation
└── unit/
    ├── test_sanitization.py   # SQL validation rules
    ├── test_query_service.py  # Service logic with mocked warehouse
    └── test_access_control.py # Middleware capability checks
```

**Live Snowflake credentials**: Stored in `.env` (see `.env.example` for variable names). Never commit credentials to version control.

Unit tests mock the warehouse layer. Integration tests hit real Snowflake.

---

## Low Effort Version (MVP)

The absolute minimum to demonstrate the core loop:

1. **QueryRecord model + migration** — persist query state
2. **Snowflake warehouse adapter** — submit async, poll status, fetch results
3. **Two endpoints**: `POST /queries` and `GET /queries/{id}`
4. **Basic SQL sanitization** — block DDL/DML, single-statement only
5. **No access control** — add in follow-up
6. **No crash recovery** — add in follow-up
7. **Integration test** hitting `INTERVIEW.PUBLIC` on Snowflake

This is roughly a single-file-exportable solution for the interview requirement.

## High Effort Version (Full Platform)

Everything in the module map above, plus:

1. Full crash recovery with startup reconciliation
2. Access control middleware with env-var capabilities
3. Comprehensive sanitization with configurable rule sets
4. Query listing with pagination, filtering by status
5. Structured logging with query lifecycle events
6. OTel tracing across the Snowflake call chain
7. Result pagination for large result sets

---

## Possible Future Extensions

- **Multi-warehouse support** — BigQuery, Redshift, Databricks via the `AbstractWarehouse` interface
- **Token-based RBAC** — replace env-var gating with JWT scopes
- **UI layer** — Streamlit dashboard, React frontend, or agent tool-use interface (MCP server)
- **Query cost estimation** — pre-flight cost check before submission
- **Result storage** — S3/GCS for large result sets instead of JSON in Postgres
- **Scheduled queries** — cron-based recurring query execution
- **Query templates** — parameterized queries with variable substitution
- **Webhooks/notifications** — callback on query completion
- **Rate limiting** — per-user query submission throttling
- **Agent interface** — expose as MCP tools for AI agent integration

---

## Sub-PRD Breakdown (Planned)

This planning PRD will be decomposed into these implementation PRDs:

| Sub-PRD | Scope | Dependencies |
|---------|-------|-------------|
| **PRD-002: Core Query Engine** | Model, schema, warehouse adapter, service, two endpoints, integration test | None |
| **PRD-003: Query Sanitization** | Middleware, validation rules, unit tests | PRD-002 |
| **PRD-004: Crash Recovery** | Startup reconciliation, recovery service, recovery tests | PRD-002 |
| **PRD-005: Access Control** | Middleware, env-var capabilities, config additions | PRD-002 |
| **PRD-006: UI / Agent Interface** | TBD — Streamlit, frontend, or MCP tools | PRD-002 through PRD-005 |

---

## Open Questions

1. **Multi-tenancy** — Will different users see only their own queries, or is this single-tenant for Phase 1?
2. **UI choice** — Streamlit (fastest), React (most flexible), or MCP agent tools (most novel)?
3. **Result size limits** — What's the max result set we store in Postgres JSON before needing object storage?
4. **Warehouse repository vs app repository** — Current `AbstractRepository` is typed to `SQLModel`. Warehouse layer is a different abstraction. Confirm this is the right separation.
5. **Agent interface** — Should we plan MCP tool schemas now or defer entirely?

## Approval State

| Status | Date | Notes |
|--------|------|-------|
| Draft | 2026-04-07 | Initial draft |
