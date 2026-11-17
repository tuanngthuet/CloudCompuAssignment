#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
docker compose build app
docker compose --profile test up -d test-db test-redis
docker compose --profile events up -d sqs
TEST_SQS_ENDPOINT_URL=http://sqs:9324 docker compose --profile test run --rm test
node tests/app/ui.test.mjs
python3 scripts/tests/check-infra.py --terraform "${TERRAFORM_BIN:-terraform}"
