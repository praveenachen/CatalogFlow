# Portfolio notes

## Description

CatalogFlow is a full-stack ETL and data-quality system for messy merchant catalogs. It preserves source data, detects schema drift, applies deterministic normalization and confidence scoring, routes ambiguity to human review, and exports only policy-qualified canonical records through local or S3/Databricks execution paths.

## Resume bullets

- Built a FastAPI, Pandas, React, and TypeScript catalog-quality pipeline that profiles and maps inconsistent CSV schemas, normalizes product data with field-level provenance, and separates processed records from publishable output.
- Designed an explainable review boundary using deterministic confidence components, validation rules, duplicate candidates, and immutable automation confidence so ambiguous records cannot silently enter the clean export.
- Implemented interchangeable local and production adapters for filesystem/S3 storage and Pandas/Databricks processing, with processing-run lifecycle tracking, Delta medallion outputs, migrations, and mocked cloud-contract tests.

## Interview answers

### What problem does it solve?

Merchant feeds often describe the same product concepts with different headers and inconsistent values. CatalogFlow makes that variation explicit, transforms what it can prove, and holds risky records for review before downstream publication.

### Why is this an ETL problem?

The system extracts uploaded source rows, transforms them into a canonical product contract with quality evidence, and loads both complete processed data and a policy-filtered consumption layer. Profiling, lineage, replay, and publication gating are core ETL concerns rather than simple form validation.

### Why Pandas and Databricks?

Pandas keeps local development and deterministic tests lightweight. Databricks supplies a managed production execution and Delta publication boundary. Today the Databricks task reuses the Pandas kernel for rule parity; native distributed Spark is future work, not a current claim.

### Why S3?

S3 provides durable, immutable source objects and replayable bulk artifacts without putting CSV bytes into the transactional database. Deterministic keys, checksums, private access, and encryption metadata make the storage contract testable.

### Why not use an LLM for mapping?

Mapping errors can corrupt an entire batch. Exact rules, reviewed aliases, and gated fuzzy candidates are reproducible and explainable, and they can deliberately return "unresolved." An LLM would require a labeled evaluation set, guardrails, and a deterministic fallback before it would be appropriate here.

### How does confidence scoring work?

It is a weighted heuristic over schema mapping, required-field completeness, value validity, normalization certainty, and entity certainty. The score is evidence for routing, not a calibrated probability, and its components remain inspectable.

### Why include human review?

Some ambiguity is real: two similar names may be separate products, and an invalid source value may need domain context. Review captures an explicit decision while validation prevents a reviewer from publishing structurally invalid canonical data.

### How does it prevent silent corruption?

The system preserves raw values, records every normalization rule, refuses low-confidence automatic mappings, flags duplicates without merging, keeps automation and human state separate, and applies one publish policy to APIs, Gold artifacts, and clean exports.

### What are Bronze, Silver, and Gold here?

Bronze is the exact source plus ingestion metadata. Silver is every processed record with raw/canonical values and quality evidence. Gold is the subset currently allowed by publication policy.

### What changes at larger scale?

The deterministic contracts should remain, but CSV parsing and transformations would move to partitioned Spark DataFrames, review updates would use an outbox/event workflow, batch history would gain operational monitoring, and thresholds would be calibrated against labeled outcomes.
