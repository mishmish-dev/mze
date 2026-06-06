from unittest.mock import MagicMock, patch

import pytest

from mze.executor import MAX_OUTPUT_SIZE, add_command, run_command


def test_arity_mismatch(tmp_path, clean_db):
    add_command("two-args", "diff {0} {1}", clean_db)
    f1 = tmp_path / "f1.txt"
    f1.write_text("a")

    # Too few args
    with pytest.raises(SystemExit) as e:
        run_command("two-args", [str(f1)], clean_db)
    assert e.value.code == 1

    # Too many args
    f2 = tmp_path / "f2.txt"
    f2.write_text("b")
    f3 = tmp_path / "f3.txt"
    f3.write_text("c")
    with pytest.raises(SystemExit) as e:
        run_command("two-args", [str(f1), str(f2), str(f3)], clean_db)
    assert e.value.code == 1


def test_non_zero_exit_code(tmp_path, clean_db):
    add_command("fail-cmd", "false", clean_db)  # 'false' always returns 1
    f1 = tmp_path / "f1.txt"
    f1.write_text("a")

    with pytest.raises(SystemExit) as e:
        run_command("fail-cmd", [str(f1)], clean_db)
    assert e.value.code == 1


def test_stderr_capture(tmp_path, clean_db):
    add_command("err-cmd", "echo 'error' >&2", clean_db)
    f1 = tmp_path / "f1.txt"
    f1.write_text("a")

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=b"", stderr=b"error\n", returncode=0)
        with patch("sys.stderr.buffer.write") as mock_stderr:
            with pytest.raises(SystemExit) as e:
                run_command("err-cmd", [], clean_db)
            assert e.value.code == 0
            # Verify stderr was written
            mock_stderr.assert_called()


def test_max_output_size(tmp_path, clean_db):
    add_command("big-cmd", "cat {}", clean_db)
    f1 = tmp_path / "big.txt"
    # Create a file slightly larger than MAX_OUTPUT_SIZE
    f1.write_bytes(b"x" * (MAX_OUTPUT_SIZE + 1))

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            stdout=b"x" * (MAX_OUTPUT_SIZE + 1), stderr=b"", returncode=0
        )

        # First run (Miss)
        with pytest.raises(SystemExit) as e:
            run_command("big-cmd", [str(f1)], clean_db)
        assert e.value.code == 0
        assert mock_run.call_count == 1

        # Second run (Should still be a Miss because of size limit)
        with pytest.raises(SystemExit) as e:
            run_command("big-cmd", [str(f1)], clean_db)
        assert e.value.code == 0
        assert mock_run.call_count == 2
