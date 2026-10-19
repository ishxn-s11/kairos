"""Account persistence: local SQLite or a pooled PostgreSQL URL on Vercel."""

from __future__ import annotations

import hashlib
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from threading import Lock


class AccountDatabaseUnavailable(RuntimeError):
    """A safe, public error that never includes database credentials."""


_initialized: set[str] = set()
_schema_lock = Lock()


def _schema(postgres: bool) -> tuple[str, ...]:
    identity = "BIGSERIAL PRIMARY KEY" if postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"
    reference = "BIGINT" if postgres else "INTEGER"
    email = "TEXT NOT NULL UNIQUE" if postgres else "TEXT NOT NULL UNIQUE COLLATE NOCASE"
    return (
        f"""CREATE TABLE IF NOT EXISTS users (
            id {identity}, name TEXT NOT NULL, email {email},
            password_hash TEXT NOT NULL, created_at TEXT NOT NULL
        )""",
        f"""CREATE TABLE IF NOT EXISTS sessions (
            token_hash TEXT PRIMARY KEY,
            user_id {reference} NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at TEXT NOT NULL, expires_at TEXT NOT NULL
        )""",
        f"""CREATE TABLE IF NOT EXISTS actions (
            id {identity},
            user_id {reference} NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            action TEXT NOT NULL, details_json TEXT NOT NULL DEFAULT '{{}}',
            created_at TEXT NOT NULL
        )""",
        "CREATE INDEX IF NOT EXISTS actions_user_created ON actions(user_id, created_at DESC)",
    )


class _Connection:
    """Run the application's fixed, parameterized SQL on either database."""

    def __init__(self, connection, postgres: bool):
        self.connection = connection
        self.postgres = postgres

    def execute(self, sql: str, params=()):
        if self.postgres:
            # SQL is supplied only by this application; values remain bound params.
            sql = sql.replace("?", "%s")
            from psycopg.errors import UniqueViolation

            try:
                return self.connection.execute(sql, params)
            except UniqueViolation as exc:
                raise sqlite3.IntegrityError("duplicate account") from exc
        return self.connection.execute(sql, params)


@contextmanager
def account_database(path: str, database_url: str = "", *, schema_url: str = "", serverless: bool = False):
    postgres = bool(database_url)
    if serverless and not postgres:
        raise AccountDatabaseUnavailable("Account storage is not configured. Set DATABASE_URL.")
    connection = None
    try:
        if postgres:
            import psycopg
            from psycopg.rows import dict_row

            connection = psycopg.connect(database_url, row_factory=dict_row, connect_timeout=10)
            key = hashlib.sha256(database_url.encode()).hexdigest()
        else:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(path, timeout=10)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            key = str(Path(path).resolve())
        db = _Connection(connection, postgres)
        with _schema_lock:
            if key not in _initialized:
                schema_connection = connection
                if postgres and schema_url:
                    # DDL uses Neon's direct endpoint; normal traffic stays pooled.
                    schema_connection = psycopg.connect(schema_url, row_factory=dict_row, connect_timeout=10)
                try:
                    schema_db = _Connection(schema_connection, postgres)
                    for statement in _schema(postgres):
                        schema_db.execute(statement)
                    schema_connection.commit()
                finally:
                    if schema_connection is not connection:
                        schema_connection.close()
                _initialized.add(key)
        try:
            yield db
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    except (sqlite3.IntegrityError, AccountDatabaseUnavailable):
        raise
    except Exception as exc:
        raise AccountDatabaseUnavailable("Account storage is temporarily unavailable. Please try again.") from exc
    finally:
        if connection is not None:
            connection.close()
