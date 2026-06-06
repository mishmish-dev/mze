import pytest
from pathlib import Path
from mze.file_list_hash import compute_hash

def test_compute_hash_consistency(tmp_path):
    f1 = tmp_path / "file1.txt"
    f1.write_text("hello world")
    f2 = tmp_path / "file2.txt"
    f2.write_text("foo bar")

    files = [str(f1), str(f2)]
    hash1 = compute_hash(files)
    hash2 = compute_hash(files)
    assert hash1 == hash2

def test_compute_hash_order_sensitivity(tmp_path):
    f1 = tmp_path / "file1.txt"
    f1.write_text("hello world")
    f2 = tmp_path / "file2.txt"
    f2.write_text("foo bar")

    hash1 = compute_hash([str(f1), str(f2)])
    hash2 = compute_hash([str(f2), str(f1)])
    assert hash1 != hash2

def test_compute_hash_content_sensitivity(tmp_path):
    f1 = tmp_path / "file1.txt"
    f1.write_text("hello world")
    f2 = tmp_path / "file2.txt"
    f2.write_text("foo bar")

    files = [str(f1), str(f2)]
    hash1 = compute_hash(files)

    f1.write_text("hello worle") # change one byte
    hash2 = compute_hash(files)
    assert hash1 != hash2

def test_compute_hash_empty_files(tmp_path):
    f1 = tmp_path / "empty1.txt"
    f1.write_text("")
    f2 = tmp_path / "empty2.txt"
    f2.write_text("")

    hash1 = compute_hash([str(f1)])
    hash2 = compute_hash([str(f2)])
    # Both are empty, so hashes should be identical
    assert hash1 == hash2

def test_compute_hash_large_files(tmp_path):
    f1 = tmp_path / "large.txt"
    content = b"a" * (2 * 1024 * 1024) # 2MB
    f1.write_bytes(content)

    hash1 = compute_hash([str(f1)])

    # Re-calculate manually if needed or just check consistency
    hash2 = compute_hash([str(f1)])
    assert hash1 == hash2

