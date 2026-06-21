// mze: memoizing command executor.
// ponytail: single file — the whole thing is a CLI over a tiny KV store.

use std::fs::{self};
use std::io::{self, Write};
use std::path::{Path, PathBuf};
use std::process::{Command, exit};

use clap::{Parser, Subcommand};
use rusqlite::{Connection, OptionalExtension, params};

const MAX_OUTPUT_SIZE: usize = 10 * 1024 * 1024; // 10 MiB

#[derive(Parser)]
#[command(about = "mze: Memoizing command executor")]
struct Cli {
    /// Base directory for the mze database
    #[arg(long, global = true)]
    base_dir: Option<String>,
    #[command(subcommand)]
    cmd: Cmd,
}

#[derive(Subcommand)]
enum Cmd {
    /// Save a command template
    Add {
        name: String,
        cmd: String,
        /// Install a thin wrapper for this command
        #[arg(long)]
        install: bool,
        #[arg(long, default_value_t = default_bin_dir())]
        bin_dir: String,
    },
    /// Run a saved command with files
    Run { name: String, files: Vec<String> },
    /// List saved commands
    List,
    /// Delete a saved command
    Remove {
        name: String,
        #[arg(long, default_value_t = default_bin_dir())]
        bin_dir: String,
    },
    /// Install the mze binary into bin-dir
    Install {
        #[arg(long, default_value_t = default_bin_dir())]
        bin_dir: String,
    },
}

fn home() -> PathBuf {
    PathBuf::from(std::env::var("HOME").expect("HOME not set"))
}
fn default_base_dir() -> String {
    home().join(".mze").to_string_lossy().into_owned()
}
fn default_bin_dir() -> String {
    home().join(".local/bin").to_string_lossy().into_owned()
}

fn main() {
    let cli = Cli::parse();
    let base = PathBuf::from(cli.base_dir.unwrap_or_else(default_base_dir));
    match cli.cmd {
        Cmd::Add { name, cmd, install, bin_dir } => add_command(&name, &cmd, &base, install, &bin_dir),
        Cmd::Run { name, files } => run_command(&name, &files, &base),
        Cmd::List => list_commands(&base),
        Cmd::Remove { name, bin_dir } => remove_command(&name, &base, &bin_dir),
        Cmd::Install { bin_dir } => install_mze(&bin_dir),
    }
}

// ---- template parsing (Python str.format subset: {} and {n}) ----

enum Seg {
    Lit(String),
    Auto,
    Index(usize),
}

fn tokenize(t: &str) -> Result<Vec<Seg>, String> {
    let mut segs = Vec::new();
    let mut lit = String::new();
    let mut chars = t.chars().peekable();
    while let Some(c) = chars.next() {
        match c {
            '{' => {
                if chars.peek() == Some(&'{') {
                    chars.next();
                    lit.push('{');
                    continue;
                }
                let mut inner = String::new();
                let mut closed = false;
                while let Some(&nc) = chars.peek() {
                    if nc == '}' {
                        chars.next();
                        closed = true;
                        break;
                    }
                    if nc == '{' {
                        return Err("Invalid template syntax: unexpected '{' in field".into());
                    }
                    inner.push(nc);
                    chars.next();
                }
                if !closed {
                    return Err("Invalid template syntax: single '{' in template".into());
                }
                if !lit.is_empty() {
                    segs.push(Seg::Lit(std::mem::take(&mut lit)));
                }
                let name = inner.split([':', '!']).next().unwrap_or("");
                if name.is_empty() {
                    segs.push(Seg::Auto);
                } else if name.chars().all(|c| c.is_ascii_digit()) {
                    segs.push(Seg::Index(name.parse().unwrap()));
                } else {
                    return Err(format!(
                        "Invalid field name '{{{name}}}'; only numbers or empty braces are allowed"
                    ));
                }
            }
            '}' => {
                if chars.peek() == Some(&'}') {
                    chars.next();
                    lit.push('}');
                    continue;
                }
                return Err("Invalid template syntax: single '}' in template".into());
            }
            _ => lit.push(c),
        }
    }
    if !lit.is_empty() {
        segs.push(Seg::Lit(lit));
    }
    Ok(segs)
}

fn arity(segs: &[Seg]) -> Result<usize, String> {
    let has_auto = segs.iter().any(|s| matches!(s, Seg::Auto));
    let has_explicit = segs.iter().any(|s| matches!(s, Seg::Index(_)));
    if has_auto && has_explicit {
        return Err("Cannot mix automatic and explicit positional arguments in template".into());
    }
    if has_explicit {
        Ok(segs
            .iter()
            .filter_map(|s| if let Seg::Index(i) = s { Some(i + 1) } else { None })
            .max()
            .unwrap_or(0))
    } else {
        Ok(segs.iter().filter(|s| matches!(s, Seg::Auto)).count())
    }
}

fn parse_arity(template: &str) -> Result<usize, String> {
    arity(&tokenize(template)?)
}

fn render(segs: &[Seg], args: &[String]) -> String {
    let mut out = String::new();
    let mut auto = 0;
    for s in segs {
        match s {
            Seg::Lit(l) => out.push_str(l),
            Seg::Auto => {
                out.push_str(&args[auto]);
                auto += 1;
            }
            Seg::Index(i) => out.push_str(&args[*i]),
        }
    }
    out
}

// shlex.quote equivalent
fn shell_quote(s: &str) -> String {
    let safe = !s.is_empty()
        && s.chars()
            .all(|c| c.is_ascii_alphanumeric() || "@%_-+=:,./".contains(c));
    if safe {
        s.to_string()
    } else {
        format!("'{}'", s.replace('\'', "'\"'\"'"))
    }
}

// ---- hashing: order-dependent streaming blake3 ----

fn compute_hash(files: &[String]) -> io::Result<[u8; 32]> {
    let mut h = blake3::Hasher::new();
    h.update(b"init\0");
    for f in files {
        let size = fs::metadata(f)?.len();
        h.update(b"file\0");
        h.update(&size.to_be_bytes());
        // mmap + multithreaded SIMD; blake3 picks the strategy by input size.
        h.update_mmap_rayon(f)?;
    }
    Ok(*h.finalize().as_bytes())
}

// ---- db ----

fn get_db(db_dir: &Path) -> Connection {
    fs::create_dir_all(db_dir).expect("create db dir");
    let conn = Connection::open(db_dir.join("mze.sqlite")).expect("open db");
    conn.execute_batch(
        "CREATE TABLE IF NOT EXISTS commands (
            name TEXT PRIMARY KEY,
            command_template TEXT NOT NULL
         );
         CREATE TABLE IF NOT EXISTS memoized_results (
            command_name TEXT,
            file_contents_hash BLOB,
            output BLOB,
            PRIMARY KEY (command_name, file_contents_hash)
         );",
    )
    .expect("init db");
    conn
}

// ---- commands ----

fn add_command(name: &str, cmd: &str, db_dir: &Path, install: bool, bin_dir: &str) {
    let arity = match parse_arity(cmd) {
        Ok(a) => a,
        Err(e) => {
            eprintln!("Syntax error in command template: {e}");
            return;
        }
    };

    let db = get_db(db_dir);
    db.execute(
        "INSERT OR REPLACE INTO commands (name, command_template) VALUES (?, ?)",
        params![name, cmd],
    )
    .expect("insert command");
    println!("Saved command '{name}' with arity {arity}");

    if !install {
        return;
    }
    let bin = PathBuf::from(shellexpand(bin_dir));
    let mze_path = bin.join("mze");
    if !mze_path.is_file() {
        eprintln!("Error: mze executable not found in {}, run 'mze install' first", bin.display());
        return;
    }
    let wrapper = bin.join(name);
    let content = format!("#!/bin/sh\nexec {} run {name} \"$@\"\n", mze_path.display());
    if let Err(e) = write_executable(&wrapper, &content) {
        eprintln!("Error creating wrapper: {e}");
        return;
    }
    println!("Wrapper created at {}", wrapper.display());
}

fn list_commands(db_dir: &Path) {
    let db = get_db(db_dir);
    let mut stmt = db.prepare("SELECT name, command_template FROM commands").unwrap();
    let rows: Vec<(String, String)> = stmt
        .query_map([], |r| Ok((r.get(0)?, r.get(1)?)))
        .unwrap()
        .map(|r| r.unwrap())
        .collect();
    if rows.is_empty() {
        println!("No commands saved.");
        return;
    }
    for (name, cmd) in rows {
        let a = parse_arity(&cmd).map(|a| a.to_string()).unwrap_or_else(|_| "?".into());
        println!("{name} (arity {a}): {cmd}");
    }
}

fn remove_command(name: &str, db_dir: &Path, bin_dir: &str) {
    let db = get_db(db_dir);
    db.execute("DELETE FROM commands WHERE name = ?", params![name]).unwrap();
    db.execute("DELETE FROM memoized_results WHERE command_name = ?", params![name]).unwrap();
    println!("Deleted command '{name}'");

    let wrapper = PathBuf::from(shellexpand(bin_dir)).join(name);
    if wrapper.is_file() {
        let content = fs::read_to_string(&wrapper).unwrap_or_default();
        if content.contains(&format!("mze run {name}")) {
            let _ = fs::remove_file(&wrapper);
            println!("Removed wrapper at {}", wrapper.display());
        } else {
            eprintln!(
                "Warning: File {} exists but does not appear to be an mze wrapper. Not removing.",
                wrapper.display()
            );
        }
    } else {
        println!("Info: No wrapper found at {}", wrapper.display());
    }
}

fn run_command(name: &str, files: &[String], db_dir: &Path) {
    let db = get_db(db_dir);

    let template: Option<String> = db
        .query_row("SELECT command_template FROM commands WHERE name = ?", params![name], |r| r.get(0))
        .optional()
        .unwrap();
    let Some(template) = template else {
        eprintln!("Command '{name}' not found.");
        exit(1);
    };

    let segs = tokenize(&template).expect("stored template should be valid");
    let arity = arity(&segs).unwrap();
    if files.len() != arity {
        eprintln!("Command '{name}' expects {arity} files, but {} were provided.", files.len());
        exit(1);
    }

    let quoted: Vec<String> = files.iter().map(|f| shell_quote(f)).collect();
    let full_cmd = render(&segs, &quoted);

    let key = match compute_hash(files) {
        Ok(k) => k,
        Err(e) => {
            eprintln!("Error hashing files: {e}");
            exit(1);
        }
    };

    let memo: Option<Vec<u8>> = db
        .query_row(
            "SELECT output FROM memoized_results WHERE command_name = ? AND file_contents_hash = ?",
            params![name, &key[..]],
            |r| r.get(0),
        )
        .optional()
        .unwrap();
    if let Some(output) = memo {
        io::stdout().write_all(&output).unwrap();
        return;
    }

    let out = Command::new("sh").arg("-c").arg(&full_cmd).output();
    let out = match out {
        Ok(o) => o,
        Err(e) => {
            eprintln!("Execution error: {e}");
            exit(1);
        }
    };

    if out.stdout.len() <= MAX_OUTPUT_SIZE {
        db.execute(
            "INSERT OR REPLACE INTO memoized_results (command_name, file_contents_hash, output) VALUES (?, ?, ?)",
            params![name, &key[..], &out.stdout],
        )
        .unwrap();
    }

    io::stdout().write_all(&out.stdout).unwrap();
    if !out.stderr.is_empty() {
        io::stderr().write_all(&out.stderr).unwrap();
    }
    exit(out.status.code().unwrap_or(1));
}

fn install_mze(bin_dir: &str) {
    // ponytail: no venv — Rust ships a single static binary. Just copy it into bin_dir.
    let bin = PathBuf::from(shellexpand(bin_dir));
    let exe = std::env::current_exe().expect("current exe");
    if let Err(e) = fs::create_dir_all(&bin) {
        eprintln!("Installation failed: {e}");
        exit(1);
    }
    let dest = bin.join("mze");
    if let Err(e) = fs::copy(&exe, &dest).and_then(|_| set_executable(&dest)) {
        eprintln!("Installation failed: {e}");
        exit(1);
    }
    println!("Installed mze to {}", dest.display());
}

// ---- fs helpers ----

fn shellexpand(p: &str) -> String {
    if let Some(rest) = p.strip_prefix("~/") {
        home().join(rest).to_string_lossy().into_owned()
    } else if p == "~" {
        home().to_string_lossy().into_owned()
    } else {
        p.to_string()
    }
}

fn set_executable(p: &Path) -> io::Result<()> {
    use std::os::unix::fs::PermissionsExt;
    fs::set_permissions(p, fs::Permissions::from_mode(0o755))
}

fn write_executable(p: &Path, content: &str) -> io::Result<()> {
    if let Some(parent) = p.parent() {
        fs::create_dir_all(parent)?;
    }
    fs::write(p, content)?;
    set_executable(p)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn arity_automatic() {
        assert_eq!(parse_arity("echo {}").unwrap(), 1);
        assert_eq!(parse_arity("echo {} {}").unwrap(), 2);
        assert_eq!(parse_arity("no placeholders").unwrap(), 0);
    }

    #[test]
    fn arity_explicit() {
        assert_eq!(parse_arity("echo {0}").unwrap(), 1);
        assert_eq!(parse_arity("echo {1} {0}").unwrap(), 2);
        assert_eq!(parse_arity("echo {2} {0}").unwrap(), 3);
    }

    #[test]
    fn arity_mix_fails() {
        assert!(parse_arity("echo {} {0}").unwrap_err().contains("Cannot mix"));
    }

    #[test]
    fn invalid_field_name() {
        assert!(parse_arity("echo {name}").unwrap_err().contains("Invalid field name"));
    }

    #[test]
    fn syntax_error() {
        assert!(parse_arity("{ { }").unwrap_err().contains("Invalid template syntax"));
    }

    #[test]
    fn renders_with_quoting() {
        let segs = tokenize("diff {0} {1}").unwrap();
        let args: Vec<String> = ["a b.txt", "c.txt"].iter().map(|s| shell_quote(s)).collect();
        assert_eq!(render(&segs, &args), "diff 'a b.txt' c.txt");
    }

    #[test]
    fn hash_order_and_content_sensitive() {
        let d = std::env::temp_dir().join(format!("mze_test_{}", std::process::id()));
        fs::create_dir_all(&d).unwrap();
        let f1 = d.join("1");
        let f2 = d.join("2");
        fs::write(&f1, "hello world").unwrap();
        fs::write(&f2, "foo bar").unwrap();
        let p1 = f1.to_string_lossy().into_owned();
        let p2 = f2.to_string_lossy().into_owned();
        let h = compute_hash(&[p1.clone(), p2.clone()]).unwrap();
        assert_eq!(h, compute_hash(&[p1.clone(), p2.clone()]).unwrap());
        assert_ne!(h, compute_hash(&[p2.clone(), p1.clone()]).unwrap());
        fs::write(&f1, "hello worle").unwrap();
        assert_ne!(h, compute_hash(&[p1, p2]).unwrap());
        fs::remove_dir_all(&d).unwrap();
    }
}
