# 60-90 second demo

The main demo uses local mode and requires no AWS or Databricks account.

1. Start FastAPI and the Vite frontend.
2. Upload `frontend/public/sample-messy-catalog.csv`.
3. On Overview, point out **20 total**, **16 publishable**, and **4 attention**.
4. Use the pipeline stepper to show the deterministic stages.
5. Open Schema and inspect one source-to-canonical mapping and its evidence drawer.
6. Open Records to show that all 20 processed rows are retained, including unresolved records.
7. Open Review and select an invalid record with a correctable field.
8. Enter a valid correction and approve it. Note that the original automation confidence does not change.
9. Return to Overview or Publish and show **17 publishable** and **3 attention**.
10. Export the clean catalog and confirm unresolved review, duplicate, invalid, and rejected rows are absent.

If time permits, show the review report and dark-mode toggle. Describe S3 and Databricks as production adapters validated by mocks; do not imply that live cloud infrastructure is part of the local demo.
