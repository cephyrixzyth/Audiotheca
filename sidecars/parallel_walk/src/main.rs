//! Parallel directory walk sidecar — JSON file listing for Python subprocess calls.

use rayon::prelude::*;
use serde::Serialize;
use std::env;
use std::path::{Path, PathBuf};
use std::process;
use walkdir::WalkDir;

#[derive(Serialize)]
struct FileEntry {
    path: String,
    name: String,
    size: u64,
    is_dir: bool,
}

#[derive(Serialize)]
struct WalkResult {
    ok: bool,
    root: String,
    count: usize,
    entries: Vec<FileEntry>,
    backend: String,
    error: Option<String>,
}

fn walk(root: &Path, max_depth: usize, follow_symlinks: bool) -> Result<Vec<FileEntry>, String> {
    let entries: Vec<FileEntry> = WalkDir::new(root)
        .max_depth(max_depth)
        .follow_links(follow_symlinks)
        .into_iter()
        .par_bridge()
        .filter_map(|entry| {
            let entry = entry.ok()?;
            if entry.file_type().is_dir() {
                return None;
            }
            let meta = entry.metadata().ok()?;
            Some(FileEntry {
                path: entry.path().display().to_string(),
                name: entry.file_name().to_string_lossy().into_owned(),
                size: meta.len(),
                is_dir: false,
            })
        })
        .collect();
    Ok(entries)
}

fn main() {
    let args: Vec<String> = env::args().collect();
    let json_mode = args.iter().any(|a| a == "--json");
    let follow = args.iter().any(|a| a == "--follow-symlinks");
    let max_depth = args
        .iter()
        .position(|a| a == "--max-depth")
        .and_then(|i| args.get(i + 1))
        .and_then(|s| s.parse().ok())
        .unwrap_or(8);
    let path = args
        .iter()
        .skip(1)
        .find(|a| !a.starts_with('-') && *a != "true" && *a != "false")
        .map(PathBuf::from);

    let result = match path {
        Some(p) if p.is_dir() => match walk(&p, max_depth, follow) {
            Ok(entries) => WalkResult {
                ok: true,
                root: p.display().to_string(),
                count: entries.len(),
                entries,
                backend: "rust".into(),
                error: None,
            },
            Err(e) => WalkResult {
                ok: false,
                root: p.display().to_string(),
                count: 0,
                entries: vec![],
                backend: "rust".into(),
                error: Some(e),
            },
        },
        Some(p) => WalkResult {
            ok: false,
            root: p.display().to_string(),
            count: 0,
            entries: vec![],
            backend: "rust".into(),
            error: Some("not a directory".into()),
        },
        None => WalkResult {
            ok: false,
            root: String::new(),
            count: 0,
            entries: vec![],
            backend: "rust".into(),
            error: Some("usage: audiotheca-parallel-walk --json <root>".into()),
        },
    };

    if json_mode {
        println!("{}", serde_json::to_string(&result).unwrap_or_else(|_| "{}".into()));
    } else if !result.ok {
        eprintln!("{}", result.error.unwrap_or_else(|| "error".into()));
        process::exit(1);
    } else {
        for entry in &result.entries {
            println!("{}", entry.path);
        }
    }
}
