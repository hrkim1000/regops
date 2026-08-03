#!/bin/bash
# Create the integration-test database.
#
# Phase 0 deferred `.env.test` to "the first integration suite that needs a separate DB"; phase 1.0
# is it. The ingestion suite writes real documents, versions and observations, and running that
# against the dev database would leave a developer unable to tell seeded rows from test residue —
# and would let a failing test corrupt the state the next manual check reads.
#
# Same cluster, separate database: the point is isolation of *data*, not of infrastructure.
set -euo pipefail

TEST_DB="${REGOPS_TEST_DB:-regops_test}"
APP_USER="${REGOPS_APP_DB_USER:-regops_app}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    SELECT 'CREATE DATABASE ${TEST_DB}'
    WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = '${TEST_DB}')\gexec

    GRANT CONNECT ON DATABASE ${TEST_DB} TO ${APP_USER};
EOSQL

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$TEST_DB" <<-EOSQL
    GRANT USAGE, CREATE ON SCHEMA public TO ${APP_USER};

    ALTER DEFAULT PRIVILEGES FOR ROLE ${POSTGRES_USER} IN SCHEMA public
        GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO ${APP_USER};
    ALTER DEFAULT PRIVILEGES FOR ROLE ${POSTGRES_USER} IN SCHEMA public
        GRANT USAGE, SELECT ON SEQUENCES TO ${APP_USER};
EOSQL

echo "test database ${TEST_DB} ready"
