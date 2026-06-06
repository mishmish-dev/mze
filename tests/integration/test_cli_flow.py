import pytest
from unittest.mock import patch, MagicMock
from mze.main import add_command, run_command, list_commands, remove_command

def test_save_run_cache_lifecycle(tmp_path, clean_db):
    f1 = tmp_path / "test1.txt"
    f1.write_text("content 1")
    f1_path = str(f1)

    add_command("my-cat", "cat {}", clean_db)

    # Mock subprocess.run to track calls
    with patch("subprocess.run") as mock_run:
        # Simulate first run (Miss)
        mock_run.return_value = MagicMock(
            stdout=b"content 1\n",
            stderr=b"",
            returncode=0
        )

        # First run
        with pytest.raises(SystemExit) as e:
            run_command("my-cat", [f1_path], clean_db)
        assert e.value.code == 0
        assert mock_run.call_count == 1

        # Second run (Hit) - should not call subprocess.run
        run_command("my-cat", [f1_path], clean_db)
        assert mock_run.call_count == 1


        # Modify file -> Third run (Miss)
        f1.write_text("content 1 changed")
        with pytest.raises(SystemExit) as e:
            run_command("my-cat", [f1_path], clean_db)
        assert e.value.code == 0
        assert mock_run.call_count == 2

def test_remove_command(clean_db):
    add_command("to-remove", "echo {}", clean_db)

    # Save some results to memoize
    # Since we can't easily run real commands without files,
    # we can just check if the command is gone from the table.
    list_commands(clean_db)

    remove_command("to-remove", clean_db)

    # Now run it, should fail
    with pytest.raises(SystemExit) as e:
        run_command("to-remove", ["somefile"], clean_db)
    assert e.value.code == 1

def test_list_commands(clean_db):
    add_command("cmd1", "echo {0}", clean_db)
    add_command("cmd2", "ls {0}", clean_db)
    list_commands(clean_db)
