# CatalogFlow

CatalogFlow turns messy merchant CSV uploads into clean, review-aware product catalogs.

It is a full-stack catalog quality tool for teams that need to ingest supplier or merchant product feeds with inconsistent headers, invalid values, duplicate rows, and changing schemas. CatalogFlow detects drift, maps known fields, normalizes product data, assigns confidence scores, routes risky records to review, and exports trusted CSVs for downstream systems.

## Features

- CSV upload for merchant product catalogs
- Schema drift detection with missing, unexpected, and mapped columns
- Automatic column mapping for common supplier header variations
- Product normalization for names, prices, inventory, categories, and tags
- Duplicate detection with review-safe routing
- Explainable component scoring for every catalog record
- Human review queue for low-confidence or invalid records
- CSV exports for cleaned catalog data, review issues, and schema drift reports

## Tech Stack

- Backend: FastAPI, Python, Pandas, Pandera, Pydantic, SQLModel, RapidFuzz, Alembic
- Frontend: React, TypeScript, Vite, Tailwind CSS
- Data: SQLite locally, PostgreSQL application state in production, local files or private S3 objects, and Delta outputs on Databricks

## Repository Structure

```text
backend/
  app/
    application.py
    domain.py
    ingestion.py
    main.py
    matching.py
    models.py
    normalization.py
    pipeline_contract.py
    processing.py
    profiling.py
    quality.py
    reviews.py
    schema_mapping.py
    schemas.py
    validation.py
    database.py
  databricks/
    catalogflow_job.py
  migrations/
  tests/
  requirements.txt

frontend/
  public/
    sample-messy-catalog.csv
  src/
    App.tsx
    api.ts
    main.tsx
  package.json
```

## Getting Started

### Prerequisites

- Python 3.10+
- Node.js 18+
- npm

### Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The API runs at `http://localhost:8000`.

`DATABASE_URL` defaults to local SQLite and can be set to a PostgreSQL SQLAlchemy URL in deployed environments.

Local mode is the default and needs no AWS or Databricks credentials:

```powershell
$env:CATALOG_STORAGE = "local"
$env:CATALOG_PROCESSOR = "local"
```

Copy `.env.example` values into your secret manager or runtime environment; the application does not load or log a committed secrets file.

### Production processing

Production mode stores the immutable upload in a private S3 bucket and submits the configured Databricks Job asynchronously:

```powershell
$env:DATABASE_URL = "postgresql+psycopg://USER:PASSWORD@HOST:5432/catalogflow"
$env:CATALOG_STORAGE = "s3"
$env:AWS_REGION = "ca-central-1"
$env:AWS_S3_BUCKET = "your-private-catalog-bucket"
$env:CATALOG_PROCESSOR = "databricks"
$env:DATABRICKS_HOST = "https://your-workspace.cloud.databricks.com"
$env:DATABRICKS_JOB_ID = "123456789"
# Prefer the supported Databricks authentication chain; set DATABRICKS_TOKEN only when required.
```

Build `backend` as a wheel and install it on the Databricks job cluster, then configure `backend/databricks/catalogflow_job.py` as a notebook task. The API passes only stable job parameters (batch, merchant, raw URI, and output URIs); it is not coupled to a workspace notebook path. The task writes Bronze metadata/raw bytes, full Silver records, publishable-only Gold records, and batch metrics as Delta datasets. Its JSON task result is ingested when `/processing-runs/{run_id}/refresh` observes terminal success.

The Databricks task intentionally calls the shared deterministic transformation kernel so local and cloud classifications cannot drift. This is a correctness-first boundary: it moves execution, durable storage, scheduling, and Delta publication to Databricks, but a single CSV transform is currently bounded by the Python worker/driver memory available to that task. A native distributed Spark transform should replace that kernel only with behavioral-equivalence tests for normalization, fuzzy matching, scoring, and routing.

### Frontend

In a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open the local URL printed by Vite.

## Sample Data

A sample catalog is included at `frontend/public/sample-messy-catalog.csv`. Use it to try the upload flow and inspect schema drift detection, normalization, review routing, and export behavior.

## API

| Method | Endpoint | Description |
| --- | --- | --- |
| `POST` | `/upload-catalog` | Upload a merchant CSV, normalize records, detect drift, and persist results |
| `POST` | `/batches` | Batch-aware upload endpoint |
| `GET` | `/latest-batch` | Return the current dashboard batch summary |
| `GET` | `/batches/{batch_id}` | Return a batch summary and mappings |
| `GET` | `/processing-runs/{run_id}` | Inspect local or Databricks execution state and artifact URIs |
| `POST` | `/processing-runs/{run_id}/refresh` | Refresh an asynchronous Databricks run and ingest terminal metadata |
| `GET` | `/batches/{batch_id}/profiling` | Return column profiles and schema drift |
| `GET` | `/batches/{batch_id}/mappings` | Return mapping candidates and confidence |
| `GET` | `/batches/{batch_id}/records` | Return normalized records for a batch |
| `GET` | `/batches/{batch_id}/review-items` | Return pending review records for a batch |
| `GET` | `/catalog` | Return publishable clean records from the latest batch by default |
| `GET` | `/processed-records` | Return all retained normalized records from the latest batch by default |
| `GET` | `/review-queue` | Return unresolved records from the latest batch by default |
| `PUT` | `/review-queue/{record_id}` | Save edits for a reviewed record |
| `POST` | `/review-items/{review_item_id}/decision` | Approve, edit, or reject without changing automation confidence |
| `GET` | `/schema-drift-report` | Return the latest schema drift report |
| `GET` | `/export/cleaned-catalog` | Download cleaned catalog CSV |
| `GET` | `/export/review-report` | Download review issues CSV |
| `GET` | `/export/schema-drift-report` | Download schema drift report CSV |

## Data Flow

1. A user uploads a merchant CSV in the frontend.
2. FastAPI receives the file through `POST /upload-catalog`.
3. The configured storage adapter writes an immutable raw object locally or to S3.
4. A `ProcessingRun` is created and the configured processor is submitted.
5. Local mode runs the deterministic Pandas path synchronously; production mode returns `SUBMITTED` and Databricks is polled through the run endpoint.
6. Pandas parses the uploaded rows.
7. Profiling captures type, null, uniqueness, samples, and applicable validity rates.
8. Exact, alias, and high-confidence fuzzy field mappings are applied; ambiguous mappings remain unresolved.
9. Normalization cleans values while retaining raw rows and rule-level traces.
10. Exact duplicates are blocked and fuzzy matches become review candidates without merging records.
11. Weighted quality components assign an explainable automation score.
12. Routing marks records as approved, needs review, duplicate, or invalid.
13. Silver retains every processed record; Gold contains only auto-trusted or explicitly human-approved records.
14. SQLite or PostgreSQL stores application/workflow state while local files or S3/Delta hold bulk artifacts.

The MVP dashboard is scoped to the latest upload batch. Historical batches remain persisted and are available through batch-specific endpoints, but are not mixed into current dashboard counts, tables, review queues, or default exports.

Publishability is independent of automation confidence: automatically trusted records and explicitly human-approved records may be exported; pending, rejected, invalid, and duplicate-candidate records remain excluded until resolved.

## Engineering Notes

- Rules-based normalization keeps the MVP transparent and easy to debug.
- Confidence scores prevent the system from silently trusting every automated change.
- Human review protects downstream systems from low-quality or ambiguous records.
- Schema drift reporting makes supplier format changes visible before they break pipelines.
- Duplicate records are flagged instead of deleted to avoid accidental data loss.
- S3 is used for durable immutable source files and replay instead of database blobs or host-local production files.
- Databricks provides an isolated, schedulable batch execution path while Pandas avoids distributed overhead in local development and small tests.
- Delta provides transactional, versionable Bronze/Silver/Gold datasets and a path for schema evolution that CSV-only outputs cannot provide.
- PostgreSQL stores relational application and review state; bulk pipeline data remains in object/lakehouse storage.
- Glue, Lambda, SQS, Redshift, and Kafka are intentionally absent because upload-triggered Jobs plus status polling satisfy this phase without extra control planes.

## License

No license has been specified yet.
