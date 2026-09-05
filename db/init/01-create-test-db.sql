-- Runs once when the Postgres data volume is first initialized.
-- Creates a separate database for the pytest suite so tests never touch
-- the same rows the demo/dev database uses.
SELECT 'CREATE DATABASE buildgate_test' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'buildgate_test')\gexec
