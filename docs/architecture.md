# Architecture

## System

```mermaid
flowchart TB
    React[React + TypeScript workspace] -->|CSV, review decisions, exports| FastAPI[FastAPI]
    FastAPI --> Batch[(UploadBatch / ProcessingRun / review state)]
    FastAPI --> Storage{CatalogStorage port}
    FastAPI --> Processor{CatalogProcessor port}
    Storage --> LocalStorage[LocalCatalogStorage]
    Storage --> S3Storage[S3CatalogStorage]
    Processor --> Pandas[PandasCatalogProcessor]
    Processor --> DBX[DatabricksCatalogProcessor]
    LocalStorage --> Bronze[Bronze: exact source]
    S3Storage --> Bronze
    Pandas --> Silver[Silver: processed + quality metadata]
    DBX --> Silver
    Silver --> Review[Human review boundary]
    Silver --> Gold[Gold: publishable only]
    Review -->|valid approval or correction| Gold
    Review -->|pending, invalid, duplicate, rejected| Excluded[Excluded from clean export]
    Gold --> Export[Canonical CSV export]
```

FastAPI owns orchestration and relational workflow state. Storage and processor interfaces select local or cloud implementations explicitly. Local execution is synchronous. Databricks submission is asynchronous and is reconciled through the processing-run refresh endpoint.

## Pipeline

```mermaid
flowchart LR
    Ingest[INGEST] --> Profile[PROFILE]
    Profile --> Map[MAP]
    Map --> Validate[VALIDATE]
    Validate --> Normalize[NORMALIZE]
    Normalize --> Match[MATCH]
    Match --> Score[SCORE]
    Score --> Route{Confident and valid?}
    Route -->|yes| Publish[PUBLISH]
    Route -->|no| Review[REVIEW]
    Review -->|valid approval or correction| Publish
    Review -->|unresolved or rejected| Hold[HOLD]
```

The current implementation maps before row normalization, then validates normalized canonical values. The diagram describes the logical evidence flow: validation and normalization traces jointly influence scoring and routing.

## Medallion model

```mermaid
flowchart LR
    Source[Merchant CSV] --> Bronze[Bronze<br/>Exact bytes + ingestion metadata]
    Bronze --> Silver[Silver<br/>All processed records<br/>Raw + canonical + quality evidence]
    Silver --> Gate{Central publish policy}
    Gate -->|allowed| Gold[Gold<br/>Canonical publishable records only]
    Gate -->|attention required| Queue[Review queue]
    Queue -->|valid human resolution| Gold
```

## Invariants

- Raw bytes and row-level source values are preserved.
- Processed/Silver records include every automation outcome.
- Gold and the clean CSV use the same centralized publish policy.
- Pending Needs Review, Duplicate, Invalid, and Rejected records are excluded.
- Human approval can resolve ambiguity but cannot waive invalid canonical data.
- Automation confidence is immutable across human review.
- Default dashboard, review, record, and export queries are scoped to the latest batch.
- An explicit unknown batch ID returns `404` and never falls through to historical data.

## Local contract

`LocalCatalogStorage` writes deterministic per-batch paths under `.catalogflow-data`. `PandasCatalogProcessor` executes synchronously and persists JSONL Silver/Gold artifacts. SQLite is the default application-state database. No AWS or Databricks credentials are read or required.

## Production contract

`S3CatalogStorage` writes private, server-side-encrypted objects with deterministic keys and SHA-256 metadata. `DatabricksCatalogProcessor` submits the configured job and records its external run ID; submission and refresh failures remain failures and never invoke Pandas locally.

The Databricks task preserves Bronze bytes, invokes the shared deterministic Pandas kernel, and writes Delta layers. This is a correctness-first cloud execution boundary, not a claim of distributed Spark transformation. PostgreSQL is intended for relational application state while S3/Delta holds bulk artifacts.
