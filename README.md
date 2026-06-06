# mze

Memoizing command executor.

`mze` allows you to save command templates and run them against files, memoizing the output based on the hash of the file contents to avoid redundant executions.

## Usage
Run `mze` via `uv run`:
```bash
uv run mze [command] [args]
```

### Commands

#### Add a command template
```bash
uv run mze add <name> "<template>" [--install] [--bin-dir <dir>]
```
Templates use Python format string syntax. For example:
```bash
uv run mze add my-tool "cat {}"
uv run mze add multi-tool "diff {0} {1}"
```
You can optionally register a command user-wise, making it runnable directly as `<name>`:
```bash
uv run mze add my-tool "cat {}" --install
```
This creates a small executable in your bin directory (default: `~/.local/bin`) that calls the command directly.

#### Run a saved command
```bash
uv run mze run <name> <file1> [file2 ...]
```
If the contents of the files haven't changed since the last run, `mze` will return the memoized output instantly.

#### List saved commands
```bash
uv run mze list
```

#### Remove a saved command
```bash
uv run mze remove <name> [--bin-dir <dir>]
```
Removes a saved command template and, if registered user-wise, also removes the executable.

#### Install mze as a tool
Install `mze` into a dedicated environment and create a wrapper script in your bin directory. Run this from the project root:
```bash
uv run mze install [--base-dir <dir>] [--bin-dir <dir>]
```
- `--base-dir`: Base directory for the environment (default: `~/.mze`).
- `--bin-dir`: Directory for the wrapper executable (default: `~/.local/bin`).

## Setup
```bash
uv sync
```
