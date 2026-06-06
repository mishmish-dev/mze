import mmap
from pathlib import Path
from blake3 import blake3


def compute_hash(files: list[str]) -> bytes:
    """
    Order-dependent streaming hash using mmap + native BLAKE3.
    """

    h = blake3()

    # global domain separation
    h.update(b"init\0")

    for f in files:
        p = Path(f)
        size = p.stat().st_size

        # file boundary marker (prevents concatenation ambiguity)
        h.update(b"file\0")
        h.update(size.to_bytes(8, "big"))

        if size == 0:
            continue

        with p.open("rb") as fh:
            mm = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
            try:
                view = memoryview(mm)
                try:
                    # chunked view over memory map (avoids huge single update)
                    # still zero-copy at OS page level
                    chunk_size = 1024 * 1024  # 1MB slices for stable throughput
                    for i in range(0, size, chunk_size):
                        h.update(view[i:i + chunk_size])
                finally:
                    view.release()
            finally:
                mm.close()

    return h.digest()