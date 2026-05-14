# Integration Tests

These tests exercise the Crewline backend through HTTP using real Postgres and MinIO.

Setup and execution:

```bash
make test-integration
```

The target starts Docker Compose services, creates `crewline_test`, creates the
`crewline-test-attachments` bucket, runs Alembic migrations, and then runs
`pytest tests/integration/`.

The suite is intentionally not part of `make test` because it requires external
services. Use `REPORT_TEMPLATE.md` after a run to summarize results.
