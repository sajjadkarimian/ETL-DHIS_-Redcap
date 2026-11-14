"""Writes analysis rows to Postgres, replacing the previous run's rows."""

from importlib import resources

import psycopg


def sql(name: str) -> str:
    return resources.files(__package__).joinpath('sql', name).read_text()


def create_schema(conn: psycopg.Connection) -> None:
    conn.execute(sql('01_schema.sql'))
    conn.execute(sql('02_views.sql'))


def replace_table(conn: psycopg.Connection, table: str, rows: list[dict]) -> None:
    conn.execute(f'DELETE FROM biotopia.{table}')
    if not rows:
        return
    columns = list(rows[0])
    with conn.cursor().copy(f'COPY biotopia.{table} ({", ".join(columns)}) FROM STDIN') as copy:
        for row in rows:
            copy.write_row([row[c] for c in columns])


def start_run(conn: psycopg.Connection) -> int:
    with conn.transaction():
        return conn.execute('INSERT INTO biotopia.etl_run DEFAULT VALUES RETURNING id').fetchone()[0]


def finish_run(conn: psycopg.Connection, run_id: int, status: str, redcap_rows=None, dhis2_rows=None, error=None) -> None:
    with conn.transaction():
        conn.execute(
            'UPDATE biotopia.etl_run SET finished_at = now(), status = %s, redcap_rows = %s, dhis2_rows = %s, error = %s WHERE id = %s',
            (status, redcap_rows, dhis2_rows, error, run_id))
