# mze

Memoizing command executor.

`mze` lets you save command templates and run them against files, memoizing the output based on the BLAKE3 hash of the file contents to avoid redundant executions.

## Build

```bash
cargo build --release
```

The binary lands at `target/release/mze`.

## Usage

```bash
mze [--base-dir <dir>] <command> [args]
```

`--base-dir` sets where the SQLite database lives (default: `~/.mze`).

### Add a command template
```bash
mze add <name> "<template>" [--install] [--bin-dir <dir>]
```
Templates use Python-style format placeholders — `{}` (automatic) or `{0} {1}` (explicit). You cannot mix the two.
```bash
mze add my-tool "cat {}"
mze add multi-tool "diff {0} {1}"
```
With `--install`, a thin wrapper script is dropped in your bin directory (default `~/.local/bin`) so you can run `<name> <files>` directly. Requires `mze` to already be in that bin directory (run `mze install` first).

### Run a saved command
```bash
mze run <name> <file1> [file2 ...]
```
If the file contents are unchanged since the last run, the memoized output is returned instantly.

### List / remove
```bash
mze list
mze remove <name> [--bin-dir <dir>]
```

### Install the binary
```bash
mze install [--bin-dir <dir>]
```
Copies the running `mze` binary into your bin directory.
