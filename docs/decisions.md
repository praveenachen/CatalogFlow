# Architecture decision records

Thresholds referenced below are current heuristics, not experimentally validated performance claims.

## ADR 1: Pandas locally and Databricks for production execution

**Problem:** The same catalog rules must run in a low-friction local environment and in a durable production batch environment.

**Options:** Pandas everywhere; Spark everywhere; separate Pandas and Spark implementations; one deterministic Pandas kernel submitted through a Databricks Job.

**Chosen:** `PandasCatalogProcessor` locally and `DatabricksCatalogProcessor` for asynchronous job submission, with the job currently invoking the shared Pandas kernel.

**Why:** Local development stays credential-free and fast while production gains managed scheduling, lifecycle tracking, S3 access, and Delta publication without duplicating business rules.

**Tradeoff:** The current Databricks transformation is bounded by worker/driver memory and does not claim native distributed Spark execution.

**Reconsider when:** Catalog sizes exceed single-node memory or throughput requires partitioned Spark DataFrame transformations.

## ADR 2: S3 for bulk data, local files for development

**Problem:** Raw inputs and medallion artifacts need replayable storage without making local setup depend on cloud services.

**Options:** Database blobs; host-local files only; S3 only; a storage port with local and S3 implementations.

**Chosen:** `CatalogStorage` with `LocalCatalogStorage` and `S3CatalogStorage`.

**Why:** Both implementations preserve the same deterministic object layout and checksum contract. S3 provides durable private object storage; local files keep the demo self-contained.

**Tradeoff:** Two adapters must remain behaviorally consistent, and local files are not appropriate shared production storage.

**Reconsider when:** Additional object stores or retention/lifecycle policies require a broader storage abstraction.

## ADR 3: PostgreSQL for application state, object/lakehouse storage for bulk data

**Problem:** Review state, batch lifecycle, and relational references have different access patterns from raw and processed datasets.

**Options:** Store everything in PostgreSQL; store everything in S3/Delta; split transactional state from bulk artifacts.

**Chosen:** SQLite locally and PostgreSQL in production for application state; local objects or S3/Delta for bulk layers.

**Why:** Relational state benefits from transactions and indexed queries, while large immutable and analytical artifacts fit object/lakehouse storage better than database blobs.

**Tradeoff:** Cross-system consistency is orchestrated rather than provided by one database transaction.

**Reconsider when:** Operational scale requires an outbox, event log, or stronger cross-system reconciliation workflow.

## ADR 4: Deterministic and fuzzy schema mapping instead of LLM mapping

**Problem:** Merchant column names vary, but an incorrect automatic mapping can silently corrupt every row.

**Options:** Manual mapping only; LLM inference; deterministic exact/alias/fuzzy mapping with confidence gates.

**Chosen:** Exact names, a reviewed alias table, and RapidFuzz candidates. Candidate confidence begins at `0.72`; automatic application requires `0.90`.

**Why:** The behavior is reproducible, inexpensive, explainable, testable offline, and can leave ambiguous fields unresolved.

**Tradeoff:** The alias vocabulary is limited and novel semantic names may require manual configuration.

**Reconsider when:** A labeled mapping corpus can support a measured model with deterministic fallback and strict evaluation.

## ADR 5: Deterministic confidence scoring instead of ML

**Problem:** Automation needs a review boundary, but there is no labeled production dataset for a calibrated predictive model.

**Options:** A binary rules engine; a trained ML model; a weighted deterministic score.

**Chosen:** Weighted components for schema mapping, required completeness, value validity, normalization certainty, and entity certainty. The current publish threshold is `0.85`.

**Why:** Every component and reason is visible, versionable, and testable. The score supports routing without pretending to be a learned probability.

**Tradeoff:** Weights and the `0.85` threshold are heuristics and may not match real-world risk across merchants.

**Reconsider when:** Labeled review outcomes are sufficient for calibration and drift monitoring.

## ADR 6: Flag fuzzy duplicate candidates instead of auto-merging

**Problem:** Duplicate products can inflate catalogs, but a false merge destroys distinct records.

**Options:** Ignore duplicates; auto-delete/merge; route candidates to review.

**Chosen:** Exact SKU/name-category matches and product-name similarity at `0.88` become candidates; no record is automatically merged or deleted.

**Why:** Preserving both source records is safer than destructive automation and retains evidence for a reviewer.

**Tradeoff:** Humans must resolve candidates, and the matching model is intentionally simple.

**Reconsider when:** Merchant-scoped entity resolution has labeled match data and reversible merge tooling.

## ADR 7: Human review is the publication boundary

**Problem:** Low-confidence or invalid transformations must not reach downstream consumers by default.

**Options:** Publish everything with warnings; block everything uncertain permanently; allow explicit review decisions under validation constraints.

**Chosen:** Pending records remain outside Gold. A valid approval or correction may become publishable; rejection remains excluded. Review state never overwrites automation confidence.

**Why:** This separates machine evidence from human accountability and prevents approval from waiving the canonical data contract.

**Tradeoff:** Publication can wait on human capacity, and review identity/authentication is not yet implemented.

**Reconsider when:** Organization-specific approval policies or automated escalation are required.

## ADR 8: Bronze, Silver, and Gold data model

**Problem:** Replay, debugging, review, and consumption require different representations of the same upload.

**Options:** Overwrite one cleaned dataset; retain raw plus one output; use three explicit layers.

**Chosen:** Bronze preserves exact source data, Silver retains every processed row with quality metadata, and Gold contains publishable canonical records only.

**Why:** The layers make lineage and policy boundaries explicit and allow transformations to be replayed without losing evidence.

**Tradeoff:** Storage is duplicated and layer refreshes require orchestration.

**Reconsider when:** Streaming ingestion, incremental tables, or formal data-catalog lineage requires a different physical layout.
