# Architecture

System architecture diagrams for query_scheduler.

## Request Lifecycle

```mermaid
sequenceDiagram
    participant C as Client
    participant U as Uvicorn
    participant F as FastAPI
    participant M as Middleware
    participant R as Router
    participant D as Dependencies
    participant DB as PostgreSQL

    C->>U: HTTP Request
    U->>F: ASGI
    F->>M: Middleware chain
    M->>R: Route matching
    R->>D: Inject dependencies (session, repo)
    D->>DB: Query / Mutate
    DB-->>D: Result
    D-->>R: Response data
    R-->>M: Response
    M-->>F: Response
    F-->>U: ASGI Response
    U-->>C: HTTP Response
```

## Application Structure

```mermaid
graph TB
    subgraph "Entry Point"
        APP[app.py<br/>FastAPI + Lifespan]
    end

    subgraph "Core"
        CFG[core/config.py<br/>Pydantic Settings]
        DB[core/database.py<br/>Async Engine + Sessions]
        LOG[core/logging.py<br/>structlog Setup]
        TEL[core/telemetry.py<br/>OTel Bootstrap]
        REPO[core/repository.py<br/>Abstract + SQLModel Repo]
    end

    subgraph "Domain"
        MOD[models.py<br/>SQLModel Tables]
        SCH[schemas.py<br/>Request/Response Schemas]
    end

    subgraph "Routes"
        RTR[routes/__init__.py<br/>Router Aggregation]
        HLT[routes/health.py<br/>/health + /ready]
    end

    APP --> CFG
    APP --> DB
    APP --> LOG
    APP --> TEL
    APP --> RTR
    RTR --> HLT
    HLT --> DB
    DB --> CFG
    REPO --> DB
    MOD --> SCH

    style CFG fill:#e1f5fe
    style DB fill:#e1f5fe
    style LOG fill:#e1f5fe
    style TEL fill:#e1f5fe
    style REPO fill:#e1f5fe
```

## Module Dependencies

```mermaid
graph LR
    CFG[core/config.py] --> DB[core/database.py]
    CFG --> LOG[core/logging.py]
    DB --> REPO[core/repository.py]
    CFG --> APP[app.py]
    DB --> APP
    LOG --> APP
    TEL[core/telemetry.py] --> APP
    APP --> RTR[routes/]
    RTR --> REPO

    style CFG fill:#fff3e0
    style TEL fill:#fce4ec
```

**Key rule:** `core/config.py` is the leaf dependency. All modules import from it, it imports from nothing internal. `core/telemetry.py` reads `os.environ` directly to avoid import-order coupling.

## Database Schema

```mermaid
erDiagram
    ITEM {
        int id PK
        string name
        string description
        datetime created_at
        datetime updated_at
    }
```

Extend this diagram as you add models.

## Repository Pattern

```mermaid
classDiagram
    class AbstractRepository {
        <<abstract>>
        +get(model, id) T | None
        +get_all(model, offset, limit) Sequence~T~
        +create(instance) T
        +update(instance, data) T
        +delete(instance) None
    }

    class SQLModelRepository {
        -_session: AsyncSession
        +get(model, id) T | None
        +get_all(model, offset, limit) Sequence~T~
        +create(instance) T
        +update(instance, data) T
        +delete(instance) None
    }

    AbstractRepository <|-- SQLModelRepository
    SQLModelRepository --> AsyncSession : uses
```

## Observability Pipeline

```mermaid
graph LR
    subgraph "Application"
        APP[FastAPI App]
        SDK[OTel SDK]
        SL[structlog]
    end

    subgraph "Collection"
        COL[OTel Collector]
    end

    subgraph "Storage & Visualization"
        TMP[Tempo<br/>Traces]
        PRO[Prometheus<br/>Metrics]
        GRF[Grafana<br/>Dashboards]
    end

    APP -->|traces| SDK
    SDK -->|OTLP gRPC| COL
    APP -->|structured logs| SL
    SL -->|stderr| STDOUT[stdout/stderr]
    COL -->|traces| TMP
    COL -->|spanmetrics| PRO
    TMP --> GRF
    PRO --> GRF

    style SDK fill:#e8f5e9
    style COL fill:#e8f5e9
```

Enable with `OTEL_ENABLED=true` and `docker compose --profile otel up -d`.
