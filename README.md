# CatalogFlow

CatalogFlow is an ETL and data-quality system that turns inconsistent merchant CSV feeds into trustworthy canonical product data. It automates deterministic transformations when evidence is strong and routes ambiguous, duplicate, or invalid records to human review instead of silently publishing them.

The core engineering question is: **How can messy data transformation be automated without silently corrupting ambiguous records?**

## Workflow

1. Ingest a CSV while preserving the exact source bytes and row values.
2. Profile columns and detect schema drift.
3. Map exact, known-alias, and sufficiently confident fuzzy fields.
4. Validate and normalize canonical product values with field-level traces.
5. Identify exact and fuzzy duplicate candidates without auto-merging them.
6. Calculate an explainable, deterministic confidence score.
7. Route unresolved records to human review.
8. Export only records that satisfy the centralized publish policy.

The included demo feed produces 20 processed records: 16 initially publishable and 4 requiring attention (1 Needs Review, 1 Duplicate, and 2 Invalid).

## Architecture

```mermaid
flowchart LR
    UI[React workspace] --> API[FastAPI API]
    API --> State[(SQLite local / PostgreSQL production)]
    API --> Storage{CatalogStorage}
    API --> Processor{CatalogProcessor}
    Storage --> LocalFiles[Local files]
    Storage --> S3[Private S3]
    Processor --> Pandas[Pandas processor]
    Processor --> Databricks[Databricks Job]
    Pandas --> Layers[Bronze / Silver / Gold]
    Databricks --> Layers
    Layers --> Review[Human review]
    Review --> Export[Policy-gated export]
```

See [architecture](docs/architecture.md), [engineering decisions](docs/decisions.md), and the [demo plan](docs/demo.md).

## Data-quality model

- **Raw preservation:** immutable source bytes and original row values remain available for replay and audit.
- **Schema evidence:** mappings record their method, confidence, and whether they were auto-applied.
- **Normalization evidence:** each normalized field records its original value, rule, result, and certainty.
- **Automation status:** Processed Records may be Auto-approved, Needs Review, Duplicate, or Invalid.
- **Human state:** review decisions are tracked independently and never overwrite automation confidence.
- **Publish policy:** unresolved, rejected, invalid, and duplicate-candidate records remain excluded. A valid human-approved correction can become publishable.

Current heuristic thresholds are configuration, not experimentally proven benchmarks:

| Decision | Threshold |
| --- | ---: |
| Fuzzy mapping candidate | 0.72 |
| Automatic mapping | 0.90 |
| Fuzzy duplicate candidate | 0.88 |
| Automatic publication confidence | 0.85 |

## Bronze, Silver, and Gold

- **Bronze:** exact uploaded bytes plus ingestion metadata.
- **Silver:** all processed rows, raw values, canonical values, validation issues, traces, confidence components, and duplicate evidence.
- **Gold:** canonical records allowed by the publication policy only.

Processed does not mean publishable. Silver intentionally contains records that Gold excludes.

## Local and production execution

| Concern | Local | Production path |
| --- | --- | --- |
| Storage | `LocalCatalogStorage` | `S3CatalogStorage` |
| Processing | `PandasCatalogProcessor` | `DatabricksCatalogProcessor` |
| App state | SQLite | PostgreSQL |
| Bulk layers | local JSONL files | S3-backed Delta datasets |

Local mode requires no cloud credentials. Cloud mode fails explicitly when required configuration or submission fails; it never silently falls back to local processing.

The Databricks job currently reuses the deterministic Pandas transformation kernel inside the job and writes Bronze, Silver, metrics, and Gold as Delta datasets. It provides remote execution, durable storage, scheduling, and lifecycle tracking, but it is **not yet a native distributed Spark DataFrame ETL implementation**.

## Tech stack

- Python, FastAPI, Pydantic, Pandas, Pandera, RapidFuzz, SQLModel, Alembic
- React, TypeScript, Vite, Tailwind CSS
- SQLite locally; PostgreSQL for production application state
- Local filesystem or private S3 storage
- Databricks Jobs and Delta for the production processing path

## Local setup

Prerequisites: Python 3.10+, Node.js 18+, and npm.

```powershell
git clone https://github.com/praveenachen/CatalogFlow.git
cd CatalogFlow
python -m venv backend\.venv
.\backend\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
cd backend
python -m alembic upgrade head
python -m uvicorn app.main:app --reload
```

In a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open the Vite URL, normally `http://localhost:5173`. The API and interactive documentation are available at `http://localhost:8000` and `http://localhost:8000/docs`.

Upload `frontend/public/sample-messy-catalog.csv` for the portfolio demo.

## Tests

```powershell
cd CatalogFlow
python -m pytest -q --basetemp=.pytest_tmp
npm --prefix frontend run build
npm --prefix frontend exec tsc -- --noEmit
```

The suite covers profiling, mapping, validation, normalization, duplicate detection, confidence scoring, latest-batch isolation, review invariants, Gold-only export, empty exports, local/S3 storage, and Databricks submission and lifecycle behavior.

## Cloud configuration

Copy the names from `.env.example` into your runtime environment or secret manager. Do not commit real credentials.

```powershell
$env:DATABASE_URL = "postgresql+psycopg://USER:PASSWORD@HOST:5432/catalogflow"
$env:CATALOG_STORAGE = "s3"
$env:AWS_REGION = "ca-central-1"
$env:AWS_S3_BUCKET = "your-private-catalog-bucket"
$env:CATALOG_PROCESSOR = "databricks"
$env:DATABRICKS_HOST = "https://your-workspace.cloud.databricks.com"
$env:DATABRICKS_JOB_ID = "123456789"
```

Prefer the supported Databricks authentication chain. Set `DATABRICKS_TOKEN` only when the deployment requires it.

## Engineering decisions

CatalogFlow favors deterministic, inspectable rules over probabilistic automation for mappings and scores; flags duplicate candidates instead of merging; separates relational workflow state from bulk data; and uses one publish-policy function across APIs and exports. The rationale and tradeoffs are captured in [docs/decisions.md](docs/decisions.md).

## Limitations

- CSV is the only ingestion format.
- Authentication and multi-tenant authorization are outside the current scope.
- Mapping aliases and category normalization rules are intentionally small and deterministic.
- Thresholds are heuristics and have not been calibrated on a production benchmark corpus.
- The Databricks transform runs the shared Pandas kernel on the worker/driver rather than distributed Spark DataFrame transformations.
- Live AWS and Databricks integration still requires validation in an owned cloud environment.

## Future work

- Native distributed Spark transformations with behavioral-equivalence tests.
- Merchant-specific mapping policies and approved schema versions.
- Authentication, authorization, and durable audit identities.
- Batch history comparison and operational alerting.
- Threshold calibration against labeled merchant data.

## Portfolio

Recruiter-facing copy, resume bullets, and interview prompts are in [docs/portfolio.md](docs/portfolio.md).
