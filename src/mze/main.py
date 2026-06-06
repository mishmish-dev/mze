import argparse
import subprocess
import sys
import os
import duckdb
import shlex
from pathlib import Path
from string import Formatter

from mze.file_list_hash import compute_hash

DB_DIR = Path.home() / ".mze"
DB_PATH = DB_DIR / "mze.duckdb"
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
            raise ValueError("Cannot mix automatic and explicit positional arguments in template")

        for literal_text, field_name, format_spec, conversion in fields:
            if field_name is not None:
                if field_name == "":
                    auto_count += 1
                elif field_name.isdigit():
                    idx = int(field_name)
                    max_arity = max(max_arity, idx + 1)
                else:
                    raise ValueError(f"Invalid field name '{{{field_name}}}'; only numbers or empty braces are allowed")

        if has_explicit:
            return max_arity
        return auto_count
    except ValueError as e:
        if "Cannot mix automatic" in str(e) or "Invalid field name" in str(e):
            raise e
        raise ValueError(f"Invalid template syntax: {e}")
    except Exception as e:
        raise ValueError(f"Invalid template syntax: {e}")

def get_db() -> duckdb.DuckDBPyConnection:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(DB_PATH))

def init_db(db: duckdb.DuckDBPyConnection) -> None:
    db.execute("""
        CREATE TABLE IF NOT EXISTS commands (
            name TEXT PRIMARY KEY,
            command_template TEXT,
            arity INTEGER
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

def save_command(name: str, cmd: str) -> None:
    try:
        arity = parse_template(cmd)
    except ValueError as e:
        print(f"Syntax error in command template: {e}", file=sys.stderr)
        return

    db = get_db()
    init_db(db)
    db.execute("INSERT OR REPLACE INTO commands (name, command_template, arity) VALUES (?, ?, ?)", (name, cmd, arity))
    print(f"Saved command '{name}' with arity {arity}")

def list_commands() -> None:
    db = get_db()
    init_db(db)
    results = db.execute("SELECT name, command_template, arity FROM commands").fetchall()
    if not results:
        print("No commands saved.")
        return
    for name, cmd, arity in results:
        print(f"{name} (arity {arity}): {cmd}")

def delete_command(name: str) -> None:
    db = get_db()
    init_db(db)
    db.execute("DELETE FROM commands WHERE name = ?", (name,))
    db.execute("DELETE FROM memoized_results WHERE command_name = ?", (name,))
    print(f"Deleted command '{name}'")

def run_command(name: str, files: list[str]) -> None:
    db = get_db()
    init_db(db)

    res = db.execute("SELECT command_template, arity FROM commands WHERE name = ?", (name,)).fetchone()
    if not res:
        print(f"Command '{name}' not found.", file=sys.stderr)
        sys.exit(1)

    cmd_template, arity = res

    if len(files) != arity:
        print(f"Command '{name}' expects {arity} files, but {len(files)} were provided.", file=sys.stderr)
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
    memo = db.execute("SELECT output FROM memoized_results WHERE command_name = ? AND file_contents_hash = ?", (name, key)).fetchone()
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
            check=False # We want to capture stdout/stderr regardless of exit code
        )
        stdout = process.stdout
        stderr = process.stderr

        result_output = stdout

        # Store if within size limit
        if len(result_output) <= MAX_OUTPUT_SIZE:
            db.execute("INSERT OR REPLACE INTO memoized_results (command_name, file_contents_hash, output) VALUES (?, ?, ?)",
                      (name, key, result_output))

        sys.stdout.buffer.write(result_output)
        if stderr:
            sys.stderr.buffer.write(stderr)

        sys.exit(process.returncode)

    except Exception as e:
        print(f"Execution error: {e}", file=sys.stderr)
        sys.exit(1)

def install_mze(args) -> None:
    prefix_path = Path(args.prefix).expanduser().resolve()
    bin_path = Path(args.bin).expanduser().resolve()
    venv_path = prefix_path / "env"
    wrapper_path = bin_path / "mze"

    try:
        print(f"Creating and synchronizing environment at {venv_path}...")
        prefix_path.mkdir(parents=True, exist_ok=True)

        if not Path("pyproject.toml").exists():
            print("Error: pyproject.toml not found in current directory. Please run this command from the project root.", file=sys.stderr)
            sys.exit(1)

        env = {"UV_PROJECT_ENVIRONMENT": str(venv_path), **os.environ}
        subprocess.run(["uv", "sync"], env=env, cwd=Path.cwd(), check=True)

        print(f"Creating wrapper at {wrapper_path}...")
        bin_path.mkdir(parents=True, exist_ok=True)

        # We use the executable created by pip in the venv
        venv_mze_bin = venv_path / "bin" / "mze"
        wrapper_content = f"#!/bin/sh\nexec {venv_mze_bin} \"$@\"\n"
        wrapper_path.write_text(wrapper_content)
        wrapper_path.chmod(0o755)

        print(f"Successfully installed mze to {prefix_path}")
        print(f"Wrapper created at {wrapper_path}")

    except subprocess.CalledProcessError as e:
        print(f"Installation failed during a subprocess call: {e}", file=sys.stderr)
        sys.exit(1)
    except PermissionError as e:
        print(f"Permission denied: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        sys.exit(1)

def main() -> None:
    parser = argparse.ArgumentParser(description="mze: Memoizing command executor")
    subparsers = parser.add_subparsers(dest="command")

    save_parser = subparsers.add_parser("save", help="Save a command template")
    save_parser.add_argument("name", help="Name of the saved command")
    save_parser.add_argument("cmd", help="The command template to run")

    run_parser = subparsers.add_parser("run", help="Run a saved command with files")
    run_parser.add_argument("name", help="Name of the saved command")
    run_parser.add_argument("files", nargs="*", help="Files to pass as arguments")

    subparsers.add_parser("list", help="List saved commands")

    delete_parser = subparsers.add_parser("delete", help="Delete a saved command")
    delete_parser.add_argument("name", help="Name of the saved command to delete")

    install_parser = subparsers.add_parser("install", help="Install mze environment and wrapper")
    install_parser.add_argument("--prefix", default=str(Path.home() / ".mze"), help="Base directory for the mze environment")
    install_parser.add_argument("--bin", default=str(Path.home() / ".local" / "bin"), help="Directory for the wrapper executable")

    args = parser.parse_args()

    if args.command == "save":
        save_command(args.name, args.cmd)
    elif args.command == "run":
        run_command(args.name, args.files)
    elif args.command == "list":
        list_commands()
    elif args.command == "delete":
        delete_command(args.name)
    elif args.command == "install":
        install_mze(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
