import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from string import Formatter

import duckdb

from mze.file_list_hash import compute_hash

DEFAULT_DB_DIR = Path.home() / ".mze"
MAX_OUTPUT_SIZE = 10 * 1024 * 1024  # 10 MiB


def parse_template(template: str) -> int:
    """
    Validates Python format string syntax and returns the arity.
    - Supports {} and {n}
    - Cannot mix automatic and explicit positional arguments.
    """
    formatter = Formatter()
    max_arity = 0
    auto_count = 0

    try:
        fields = list(formatter.parse(template))

        # Check for mixed positional arguments
        has_auto = any(f[1] == "" for f in fields if f[1] is not None)
        has_explicit = any(f[1].isdigit() for f in fields if f[1] is not None)
        if has_auto and has_explicit:
            raise ValueError(
                "Cannot mix automatic and explicit positional arguments in template"
            )

        for literal_text, field_name, format_spec, conversion in fields:
            if field_name is not None:
                if field_name == "":
                    auto_count += 1
                elif field_name.isdigit():
                    idx = int(field_name)
                    max_arity = max(max_arity, idx + 1)
                else:
                    raise ValueError(
                        f"Invalid field name '{{{field_name}}}'; "
                        "only numbers or empty braces are allowed"
                    )

        if has_explicit:
            return max_arity
        return auto_count
    except ValueError as e:
        if "Cannot mix automatic" in str(e) or "Invalid field name" in str(e):
            raise e
        raise ValueError(f"Invalid template syntax: {e}")
    except Exception as e:
        raise ValueError(f"Invalid template syntax: {e}")


def get_db(db_dir: Path = DEFAULT_DB_DIR) -> duckdb.DuckDBPyConnection:
    db_path = db_dir / "mze.duckdb"
    db_dir.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(db_path))


def init_db(db: duckdb.DuckDBPyConnection) -> None:
    db.execute("""
        CREATE TABLE IF NOT EXISTS commands (
            name TEXT PRIMARY KEY,
            command_template TEXT NOT NULL
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS memoized_results (
            command_name TEXT,
            file_contents_hash BLOB,
            output BLOB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (command_name, file_contents_hash)
        )
    """)


def add_command(
    name: str, cmd: str, db_dir: Path, install: bool = False, bin_dir: str = ""
) -> None:
    try:
        arity = parse_template(cmd)
    except ValueError as e:
        print(f"Syntax error in command template: {e}", file=sys.stderr)
        return

    db = get_db(db_dir)
    init_db(db)
    db.execute(
        "INSERT OR REPLACE INTO commands (name, command_template) VALUES (?, ?)",
        (name, cmd),
    )
    print(f"Saved command '{name}' with arity {arity}")

    if install:
        bin_dir_path = Path(bin_dir).expanduser().resolve()

        # Check that mze executable is present in bin_dir
        # The instruction was: "Check that mze executable is really present in bin_dir, error if not."
        mze_path = bin_dir_path / "mze"
        if not mze_path.is_file():
            print(
                f"Error: mze executable not found in {bin_dir_path}, run 'mze install' first",
                file=sys.stderr,
            )
            return

        wrapper_path = bin_dir_path / name
        wrapper_content = f'#!/bin/sh\nexec {mze_path} run {name} "$@"\n'

        try:
            bin_dir_path.mkdir(parents=True, exist_ok=True)
            wrapper_path.write_text(wrapper_content)
            wrapper_path.chmod(0o755)
            print(f"Wrapper created at {wrapper_path}")

            # Check if registered in PATH
            if shutil.which(name) != str(wrapper_path):
                print(
                    f"Warning: {name} might not be in your PATH or is shadowed by another command. Ensure {bin_dir_path} is in your PATH.",
                    file=sys.stderr,
                )

        except Exception as e:
            print(f"Error creating wrapper: {e}", file=sys.stderr)


def list_commands(db_dir: Path) -> None:
    db = get_db(db_dir)
    init_db(db)
    results = db.execute(
        "SELECT name, command_template FROM commands"
    ).fetchall()
    if not results:
        print("No commands saved.")
        return
    for name, cmd in results:
        arity = parse_template(cmd)
        print(f"{name} (arity {arity}): {cmd}")


def remove_command(name: str, db_dir: Path, bin_dir: str) -> None:
    db = get_db(db_dir)
    init_db(db)
    db.execute("DELETE FROM commands WHERE name = ?", (name,))
    db.execute("DELETE FROM memoized_results WHERE command_name = ?", (name,))
    print(f"Deleted command '{name}'")

    bin_dir_path = Path(bin_dir).expanduser().resolve()
    wrapper_path = bin_dir_path / name

    if wrapper_path.is_file():
        # Verify if it's an mze wrapper
        content = wrapper_path.read_text()
        if f"mze run {name}" in content:
            wrapper_path.unlink()
            print(f"Removed wrapper at {wrapper_path}")
        else:
            print(
                f"Warning: File {wrapper_path} exists but does not appear to be an mze wrapper. Not removing.",
                file=sys.stderr,
            )
    else:
        print(f"Info: No wrapper found at {wrapper_path}")


def run_command(name: str, files: list[str], db_dir: Path) -> None:
    db = get_db(db_dir)
    init_db(db)

    res = db.execute(
        "SELECT command_template FROM commands WHERE name = ?", (name,)
    ).fetchone()
    if not res:
        print(f"Command '{name}' not found.", file=sys.stderr)
        sys.exit(1)

    cmd_template = res[0]
    arity = parse_template(cmd_template)

    if len(files) != arity:
        print(
            f"Command '{name}' expects {arity} files, but {len(files)} were provided.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        # Quote files to handle spaces and special characters correctly in shell
        quoted_files = [shlex.quote(f) for f in files]
        full_cmd = cmd_template.format(*quoted_files)
    except Exception as e:
        print(f"Error formatting command: {e}", file=sys.stderr)
        sys.exit(1)

    key = compute_hash(files)

    # Check memoized results
    memo = db.execute(
        "SELECT output FROM memoized_results WHERE command_name = ? AND file_contents_hash = ?",
        (name, key),
    ).fetchone()
    if memo:
        # Memoized result found
        output = memo[0]
        if output is not None:
            sys.stdout.buffer.write(output)
            return

    # Run the command
    try:
        process = subprocess.run(
            full_cmd,
            shell=True,
            capture_output=True,
            check=False,  # We want to capture stdout/stderr regardless of exit code
        )
        stdout = process.stdout
        stderr = process.stderr

        result_output = stdout

        # Store if within size limit
        if len(result_output) <= MAX_OUTPUT_SIZE:
            db.execute(
                "INSERT OR REPLACE INTO memoized_results (command_name, file_contents_hash, output) VALUES (?, ?, ?)",
                (name, key, result_output),
            )

        sys.stdout.buffer.write(result_output)
        if stderr:
            sys.stderr.buffer.write(stderr)

        sys.exit(process.returncode)

    except Exception as e:
        print(f"Execution error: {e}", file=sys.stderr)
        sys.exit(1)
