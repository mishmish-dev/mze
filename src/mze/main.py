import click
from pathlib import Path

from mze.executor import add_command, list_commands, remove_command, run_command
from mze.install import install_mze

DEFAULT_DB_DIR = Path.home() / ".mze"

@click.group()
@click.option("--base-dir", default=str(DEFAULT_DB_DIR), help="Base directory for mze database")
@click.pass_context
def main(ctx: click.Context, base_dir: str) -> None:
    """mze: Memoizing command executor"""
    ctx.ensure_object(dict)
    ctx.obj["base_dir"] = Path(base_dir).expanduser().resolve()

@main.command("add", help="Save a command template")
@click.argument("name")
@click.argument("cmd")
@click.pass_context
def add(ctx: click.Context, name: str, cmd: str) -> None:
    add_command(name, cmd, ctx.obj["base_dir"])

@main.command("run", help="Run a saved command with files")
@click.argument("name")
@click.argument("files", nargs=-1)
@click.pass_context
def run(ctx: click.Context, name: str, files: tuple[str, ...]) -> None:
    run_command(name, list(files), ctx.obj["base_dir"])

@main.command("list", help="List saved commands")
@click.pass_context
def list_cmds(ctx: click.Context) -> None:
    list_commands(ctx.obj["base_dir"])

@main.command("remove", help="Delete a saved command")
@click.argument("name")
@click.pass_context
def remove(ctx: click.Context, name: str) -> None:
    remove_command(name, ctx.obj["base_dir"])

@main.command("install", help="Install mze environment and wrapper")
@click.option("--base-dir", default=str(DEFAULT_DB_DIR), help="Base directory for the mze environment")
@click.option("--bin-dir", default=str(Path.home() / ".local" / "bin"), help="Directory for the wrapper executable")
def install(base_dir: str, bin_dir: str) -> None:
    install_mze(base_dir, bin_dir)

if __name__ == "__main__":
    main()
