#!/bin/bash
# Create the least-privilege application role.
#
# Services connect as this role; migrations connect as the owner. That separation is what makes
# the audit_log REVOKE in migration 0001 actually bind — a table owner bypasses its own grants,
# so an app connecting as the owner would silently retain UPDATE and DELETE (ADR-0011).
set -euo pipefail

APP_USER="${REGOPS_APP_DB_USER:-regops_app}"
APP_PASSWORD="${REGOPS_APP_DB_PASSWORD:?REGOPS_APP_DB_PASSWORD must be set}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    DO \$\$ BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '${APP_USER}') THEN
            CREATE ROLE ${APP_USER} LOGIN PASSWORD '${APP_PASSWORD}' NOSUPERUSER NOCREATEDB NOCREATEROLE;
        END IF;
    END \$\$;

    GRANT CONNECT ON DATABASE ${POSTGRES_DB} TO ${APP_USER};
    GRANT USAGE ON SCHEMA public TO ${APP_USER};

    -- Default privileges for tables the migration role creates later.
    ALTER DEFAULT PRIVILEGES FOR ROLE ${POSTGRES_USER} IN SCHEMA public
        GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO ${APP_USER};
    ALTER DEFAULT PRIVILEGES FOR ROLE ${POSTGRES_USER} IN SCHEMA public
        GRANT USAGE, SELECT ON SEQUENCES TO ${APP_USER};
EOSQL

echo "app role ${APP_USER} ready"
