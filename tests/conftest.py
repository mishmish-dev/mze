import pytest
from pathlib import Path
import mze.executor

@pytest.fixture(scope="session")
def session_db_dir(tmp_path_factory):
    """
    Creates a temporary directory for the database for the entire test session.
    """
    return tmp_path_factory.mktemp("mze_db")

@pytest.fixture
def db_conn(session_db_dir):
    """
    Provides a DuckDB connection and ensures the database is initialized.
    """
    conn = mze.executor.get_db(session_db_dir)
    mze.executor.init_db(conn)
    yield conn
    conn.close()

@pytest.fixture
def clean_db(db_conn, session_db_dir):
    """
    Ensures a completely clean database for each test.
    """
    db_conn.execute("DELETE FROM commands")
    db_conn.execute("DELETE FROM memoized_results")
    return session_db_dir
