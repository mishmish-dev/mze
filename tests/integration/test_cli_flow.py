import pytest
from unittest.mock import patch, MagicMock
from mze.main import save_command, run_command, list_commands, delete_command

def test_save_run_cache_lifecycle(tmp_path, clean_db):
    f1 = tmp_path / "test1.txt"
    f1.write_text("content 1")
    f1_path = str(f1)

    save_command("my-cat", "cat {}")

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
            run_command("my-cat", [f1_path])
        assert e.value.code == 0
        assert mock_run.call_count == 1

        # Second run (Hit) - should not call subprocess.run
        run_command("my-cat", [f1_path])
        assert mock_run.call_count == 1


        # Modify file -> Third run (Miss)
        f1.write_text("content 1 changed")
        with pytest.raises(SystemExit) as e:
            run_command("my-cat", [f1_path])
        assert e.value.code == 0
        assert mock_run.call_count == 2

def test_delete_command(clean_db):
    save_command("to-delete", "echo {}")

    # Save some results to memoize
    # Since we can't easily run real commands without files,
    # we can just check if the command is gone from the table.
    list_commands()

    delete_command("to-delete")

    # Now run it, should fail
    with pytest.raises(SystemExit) as e:
        run_command("to-delete", ["somefile"])
    assert e.value.code == 1

def test_list_commands(clean_db):
    save_command("cmd1", "echo {0}")
    save_command("cmd2", "ls {0}")
    list_commands()
