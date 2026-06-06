import pytest
from pathlib import Path
import mze.main

@pytest.fixture(scope="session", autouse=True)
def session_db_path(tmp_path_factory):
    """
    Override DB_PATH to use a temporary file for the entire test session.
    """
    temp_db_dir = tmp_path_factory.mktemp("mze_db")
    temp_db_path = temp_db_dir / "mze_test.duckdb"

    # Permanently override the DB_PATH for the duration of the test session
    mze.main.DB_PATH = temp_db_path
    return temp_db_path

@pytest.fixture
def db_conn(session_db_path):
    """
    Provides a DuckDB connection and ensures the database is initialized.
    """
    # Initialize the DB for each test to ensure a clean state if needed,
    # or keep it for the session. For total isolation, we should probably
    # clear the tables between tests.
    conn = mze.main.get_db()
    mze.main.init_db(conn)
    yield conn
    conn.close()

@pytest.fixture
def clean_db(db_conn):
    """
    Ensures a completely clean database for each test.
    """
    db_conn.execute("DELETE FROM commands")
    db_conn.execute("DELETE FROM memoized_results")
    return db_conn
