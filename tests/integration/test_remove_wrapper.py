import pytest
from mze.executor import remove_command

def test_remove_wrapper_success(tmp_path, clean_db):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    cmd_name = "test-cmd"
    wrapper_path = bin_dir / cmd_name
    wrapper_path.write_text(f"#!/bin/sh\nexec /path/to/mze run {cmd_name} \"$@\"\n")

    remove_command(cmd_name, clean_db, bin_dir=str(bin_dir))

    assert not wrapper_path.exists()

def test_remove_wrapper_not_mze_wrapper(tmp_path, clean_db):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    cmd_name = "test-cmd"
    wrapper_path = bin_dir / cmd_name
    wrapper_path.write_text("#!/bin/sh\necho 'hello world'\n") # Not an mze wrapper

    remove_command(cmd_name, clean_db, bin_dir=str(bin_dir))

    # Should still exist
    assert wrapper_path.exists()
    assert "#!/bin/sh" in wrapper_path.read_text()

def test_remove_wrapper_file_not_exists(tmp_path, clean_db):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    cmd_name = "test-cmd"

    # Should not raise error
    remove_command(cmd_name, clean_db, bin_dir=str(bin_dir))
