# CatalogFlow

CatalogFlow turns messy merchant CSV uploads into clean, review-aware product catalogs.

It is a full-stack catalog quality tool for teams that need to ingest supplier or merchant product feeds with inconsistent headers, invalid values, duplicate rows, and changing schemas. CatalogFlow detects drift, maps known fields, normalizes product data, assigns confidence scores, routes risky records to review, and exports trusted CSVs for downstream systems.

## Features

- CSV upload for merchant product catalogs
- Schema drift detection with missing, unexpected, and mapped columns
- Automatic column mapping for common supplier header variations
- Product normalization for names, prices, inventory, categories, and tags
- Duplicate detection with review-safe routing
- Confidence scoring for every catalog record
- Human review queue for low-confidence or invalid records
- CSV exports for cleaned catalog data, review issues, and schema drift reports

## Tech Stack

- Backend: FastAPI, Python, Pandas, Pydantic, SQLModel, SQLite
- Frontend: React, TypeScript, Vite, Tailwind CSS
- Data: CSV import and export

## Repository Structure

```text
backend/
  app/
    main.py
    models.py
    schemas.py
    services.py
    database.py
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
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The API runs at `http://localhost:8000`.

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
| `GET` | `/catalog` | Return cleaned catalog records |
| `GET` | `/review-queue` | Return records that require human review |
| `PUT` | `/review-queue/{record_id}` | Save edits for a reviewed record |
| `GET` | `/schema-drift-report` | Return the latest schema drift report |
| `GET` | `/export/cleaned-catalog` | Download cleaned catalog CSV |
| `GET` | `/export/review-report` | Download review issues CSV |
| `GET` | `/export/schema-drift-report` | Download schema drift report CSV |

## Data Flow

1. A user uploads a merchant CSV in the frontend.
2. FastAPI receives the file through `POST /upload-catalog`.
3. Pandas parses the uploaded rows.
4. Schema drift detection compares uploaded columns against the expected catalog schema.
5. High-confidence field mappings are applied automatically.
6. Normalization cleans price, inventory, category, product name, and tag values.
7. Duplicate detection flags likely duplicate products.
8. Confidence scoring assigns a trust score to each record.
9. Routing marks records as approved, needs review, duplicate, or invalid.
10. SQLite stores original values, cleaned values, issues, scores, and review metadata.
11. The frontend displays catalog metrics, cleaned records, review work, drift details, and export actions.

## Engineering Notes

- Rules-based normalization keeps the MVP transparent and easy to debug.
- Confidence scores prevent the system from silently trusting every automated change.
- Human review protects downstream systems from low-quality or ambiguous records.
- Schema drift reporting makes supplier format changes visible before they break pipelines.
- Duplicate records are flagged instead of deleted to avoid accidental data loss.
- SQLite is used for local development; a production deployment should use PostgreSQL or a managed database.

## License

No license has been specified yet.
