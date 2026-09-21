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
- Data: CSV import and export

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
    processing.py
    profiling.py
    quality.py
    reviews.py
    schema_mapping.py
    schemas.py
    validation.py
    database.py
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
3. Pandas parses the uploaded rows.
4. Profiling captures type, null, uniqueness, samples, and applicable validity rates.
5. Exact, alias, and high-confidence fuzzy field mappings are applied; ambiguous mappings remain unresolved.
6. Normalization cleans values while retaining raw rows and rule-level traces.
7. Exact duplicates are blocked and fuzzy matches become review candidates without merging records.
8. Weighted quality components assign an explainable automation score.
9. Routing marks records as approved, needs review, duplicate, or invalid.
10. SQLite or PostgreSQL stores batches, runs, mappings, raw and canonical values, traces, scores, and independent review metadata.
11. The frontend displays catalog metrics, cleaned records, review work, drift details, and export actions.

The MVP dashboard is scoped to the latest upload batch. Historical batches remain persisted and are available through batch-specific endpoints, but are not mixed into current dashboard counts, tables, review queues, or default exports.

Publishability is independent of automation confidence: automatically trusted records and explicitly human-approved records may be exported; pending, rejected, invalid, and duplicate-candidate records remain excluded until resolved.

## Engineering Notes

- Rules-based normalization keeps the MVP transparent and easy to debug.
- Confidence scores prevent the system from silently trusting every automated change.
- Human review protects downstream systems from low-quality or ambiguous records.
- Schema drift reporting makes supplier format changes visible before they break pipelines.
- Duplicate records are flagged instead of deleted to avoid accidental data loss.
- SQLite is used for local development; a production deployment should use PostgreSQL or a managed database.

## License

No license has been specified yet.
