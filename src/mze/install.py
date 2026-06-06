import os
import subprocess
import sys
from pathlib import Path


def install_mze(base_dir: str, bin_dir: str) -> None:
    base_dir_path = Path(base_dir).expanduser().resolve()
    bin_dir_path = Path(bin_dir).expanduser().resolve()
    venv_path = base_dir_path / "env"
    wrapper_path = bin_dir_path / "mze"

    try:
        print(f"Creating and synchronizing environment at {venv_path}...")
        base_dir_path.mkdir(parents=True, exist_ok=True)

        if not Path("pyproject.toml").exists():
            print(
                "Error: pyproject.toml not found in current directory. Please run this command from the project root.",
                file=sys.stderr,
            )
            sys.exit(1)

        env = {"UV_PROJECT_ENVIRONMENT": str(venv_path), **os.environ}
        if "VIRTUAL_ENV" in env:
            del env["VIRTUAL_ENV"]
        subprocess.run(["uv", "sync"], env=env, cwd=Path.cwd(), check=True)

        print(f"Creating wrapper at {wrapper_path}...")
        bin_dir_path.mkdir(parents=True, exist_ok=True)

        # We use the executable created by pip in the venv
        venv_mze_bin = venv_path / "bin" / "mze"
        wrapper_content = f'#!/bin/sh\nexec {venv_mze_bin} "$@"\n'
        wrapper_path.write_text(wrapper_content)
        wrapper_path.chmod(0o755)

        print(f"Successfully installed mze to {base_dir_path}")
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
