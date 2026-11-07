\getenv app_db_password APP_DB_PASSWORD

SELECT format(
    'CREATE ROLE ledgerline_app LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT',
    :'app_db_password'
)
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'ledgerline_app')
\gexec

ALTER ROLE ledgerline_app WITH LOGIN PASSWORD :'app_db_password'
    NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;

SELECT format('REVOKE %I FROM ledgerline_app', granted_role.rolname)
FROM pg_auth_members membership
JOIN pg_roles granted_role ON granted_role.oid = membership.roleid
WHERE membership.member = 'ledgerline_app'::regrole
\gexec

GRANT CONNECT ON DATABASE ledgerline TO ledgerline_app;
REVOKE CREATE ON DATABASE ledgerline FROM ledgerline_app;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE CREATE ON SCHEMA public FROM ledgerline_app;
GRANT USAGE ON SCHEMA public TO ledgerline_app;

ALTER DEFAULT PRIVILEGES FOR ROLE ledgerline_user
    REVOKE ALL ON TABLES FROM ledgerline_app;
ALTER DEFAULT PRIVILEGES FOR ROLE ledgerline_user
    REVOKE ALL ON SEQUENCES FROM ledgerline_app;
ALTER DEFAULT PRIVILEGES FOR ROLE ledgerline_user
    REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
