import pytest
import os
from pathlib import Path
from mze.executor import add_command

def test_add_install_success(tmp_path, clean_db):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    # Create a fake mze executable in bin_dir
    mze_path = bin_dir / "mze"
    mze_path.write_text("#!/bin/sh\necho 'fake mze'\n")
    mze_path.chmod(0o755)

    cmd_name = "test-cmd"
    add_command(cmd_name, "echo {0}", clean_db, install=True, bin_dir=str(bin_dir))

    wrapper_path = bin_dir / cmd_name
    assert wrapper_path.exists()

    # Check content
    content = wrapper_path.read_text()
    assert f"exec {mze_path} run {cmd_name}" in content

    # Check permissions (executable)
    assert os.access(wrapper_path, os.X_OK)

def test_add_install_failure_no_mze(tmp_path, clean_db):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    # NO mze executable in bin_dir

    cmd_name = "test-cmd-fail"
    # Capture stderr to check for error message
    import sys
    from io import StringIO

    captured_stderr = StringIO()
    sys.stderr = captured_stderr

    add_command(cmd_name, "echo {0}", clean_db, install=True, bin_dir=str(bin_dir))

    sys.stderr = sys.__stderr__

    wrapper_path = bin_dir / cmd_name
    assert not wrapper_path.exists()
    assert "Error: mze executable not found" in captured_stderr.getvalue()
