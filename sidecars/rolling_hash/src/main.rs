//! Rolling full-file hash sidecar — JSON output for Python subprocess calls.

use md5::Context;
use serde::Serialize;
use std::env;
use std::fs::File;
use std::io::Read;
use std::path::PathBuf;
use std::process;

#[derive(Serialize)]
struct HashResult {
    ok: bool,
    path: String,
    hash: Option<String>,
    size: u64,
    algorithm: String,
    backend: String,
    error: Option<String>,
}

fn hash_file(path: &PathBuf) -> Result<(String, u64), String> {
    let mut file = File::open(path).map_err(|e| e.to_string())?;
    let size = file.metadata().map_err(|e| e.to_string())?.len();
    let mut context = Context::new();
    let mut buffer = [0u8; 1024 * 1024];
    loop {
        let n = file.read(&mut buffer).map_err(|e| e.to_string())?;
        if n == 0 {
            break;
        }
        context.consume(&buffer[..n]);
    }
    Ok((format!("{:x}", context.compute()), size))
}

fn main() {
    let args: Vec<String> = env::args().collect();
    let json_mode = args.iter().any(|a| a == "--json");
    let path = args
        .iter()
        .skip(1)
        .find(|a| !a.starts_with('-'))
        .map(PathBuf::from);

    let result = match path {
        Some(p) if p.is_file() => match hash_file(&p) {
            Ok((hash, size)) => HashResult {
                ok: true,
                path: p.display().to_string(),
                hash: Some(hash),
                size,
                algorithm: "md5".into(),
                backend: "rust".into(),
                error: None,
            },
            Err(e) => HashResult {
                ok: false,
                path: p.display().to_string(),
                hash: None,
                size: 0,
                algorithm: "md5".into(),
                backend: "rust".into(),
                error: Some(e),
            },
        },
        Some(p) => HashResult {
            ok: false,
            path: p.display().to_string(),
            hash: None,
            size: 0,
            algorithm: "md5".into(),
            backend: "rust".into(),
            error: Some("not a file".into()),
        },
        None => HashResult {
            ok: false,
            path: String::new(),
            hash: None,
            size: 0,
            algorithm: "md5".into(),
            backend: "rust".into(),
            error: Some("usage: audiotheca-rolling-hash --json <path>".into()),
        },
    };

    if json_mode {
        println!("{}", serde_json::to_string(&result).unwrap_or_else(|_| "{}".into()));
    } else if result.ok {
        println!("{}", result.hash.unwrap_or_default());
    } else {
        eprintln!("{}", result.error.unwrap_or_else(|| "error".into()));
        process::exit(1);
    }
}
