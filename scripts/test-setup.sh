#!/usr/bin/env bash
set -euo pipefail

export PGPASSWORD="${PGPASSWORD:-crewline}"

if pg_isready -h localhost -p 5432 -U crewline > /dev/null 2>&1; then
  echo "Using existing Postgres on localhost:5432."
  docker compose up -d minio minio-init
else
  docker compose up -d postgres minio minio-init
fi

echo "Waiting for Postgres..."
until pg_isready -h localhost -p 5432 -U crewline > /dev/null 2>&1; do
  sleep 1
done

psql -h localhost -U crewline -d postgres -tc "SELECT 1 FROM pg_database WHERE datname = 'crewline_test'" \
  | grep -q 1 || psql -h localhost -U crewline -d postgres -c "CREATE DATABASE crewline_test;"

echo "Ensuring MinIO test bucket exists..."
docker compose run --rm --entrypoint /bin/sh minio-init -c "
  mc alias set local http://minio:9000 minioadmin minioadmin;
  mc mb --ignore-existing local/crewline-test-attachments;
  mc anonymous set download local/crewline-test-attachments;
" >/dev/null

DATABASE_URL=postgresql+asyncpg://crewline:crewline@localhost:5432/crewline_test \
PM_INITIAL_PASSWORD=test_pm_password \
AGENT_BE_INITIAL_KEY=test_be_key \
AGENT_FE_INITIAL_KEY=test_fe_key \
AGENT_ARCHITECT_INITIAL_KEY=test_architect_key \
AGENT_QA_INITIAL_KEY=test_qa_key \
STORAGE_BUCKET=crewline-test-attachments \
GITHUB_APP_ID=12345 \
GITHUB_APP_CLIENT_ID=github-client-id \
GITHUB_APP_CLIENT_SECRET=github-client-secret \
GITHUB_APP_PRIVATE_KEY=test-private-key \
uv run alembic upgrade head

echo "Test environment ready."
