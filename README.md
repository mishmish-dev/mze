# mze

Memoizing command executor.

`mze` allows you to save command templates and run them against files, memoizing the output based on the hash of the file contents to avoid redundant executions.

## Usage
Run `mze` via `uv run`:
```bash
uv run mze [command] [args]
```

### Commands

#### Save a command template
```bash
uv run mze save <name> "<template>"
```
Templates use Python format string syntax. For example:
```bash
uv run mze save my-tool "cat {}"
uv run mze save multi-tool "diff {0} {1}"
```

#### Run a saved command
```bash
uv run mze run <name> <file1> [file2 ...]
```
If the contents of the files haven't changed since the last run, `mze` will return the memoized output instantly.

#### List saved commands
```bash
uv run mze list
```

#### Delete a saved command
```bash
uv run mze delete <name>
```

#### Install mze as a tool
Install `mze` into a dedicated environment and create a wrapper script in your bin directory. Run this from the project root:
```bash
uv run mze install [--prefix <dir>] [--bin <dir>]
```
- `--prefix`: Base directory for the environment (default: `~/.mze`).
- `--bin`: Directory for the wrapper executable (default: `~/.local/bin`).

## Setup
```bash
uv sync
```
