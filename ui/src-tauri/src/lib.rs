use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use tauri::{Manager, RunEvent};
use tauri_plugin_shell::process::CommandChild;
use tauri_plugin_shell::ShellExt;

const API_PORT: u16 = 8787;

enum ApiProcess {
    Sidecar(CommandChild),
    Python(Child),
}

struct ApiChild(Mutex<Option<ApiProcess>>);

fn workspace_root() -> PathBuf {
    if cfg!(debug_assertions) {
        PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("..")
            .join("..")
            .canonicalize()
            .unwrap_or_else(|_| PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../.."))
    } else if let Ok(home) = std::env::var("AUDIOTHECA_HOME") {
        PathBuf::from(home)
    } else if let Ok(exe) = std::env::current_exe() {
        exe.parent()
            .map(|dir| dir.to_path_buf())
            .unwrap_or_else(|| PathBuf::from("."))
    } else {
        PathBuf::from(".")
    }
}

fn sidecar_env(
    app: &tauri::App,
    root: &Path,
) -> (String, Option<String>) {
    let home = root.to_string_lossy().to_string();
    let engine = app
        .shell()
        .sidecar("audiotheca-engine")
        .ok()
        .and_then(|_| engine_resource_path(app));
    (home, engine.map(|p| p.to_string_lossy().to_string()))
}

fn engine_resource_path(app: &tauri::App) -> Option<PathBuf> {
    let resource = app.path().resource_dir().ok()?;
    for dir in [resource.clone(), resource.join("binaries")] {
        if let Ok(entries) = std::fs::read_dir(dir) {
            for entry in entries.flatten() {
                let name = entry.file_name().to_string_lossy().to_string();
                if name.starts_with("audiotheca-engine") {
                    return Some(entry.path());
                }
            }
        }
    }
    None
}

fn spawn_api_server(app: &tauri::App, root: &Path) -> Option<ApiProcess> {
    let (home, engine) = sidecar_env(app, root);

    if let Ok(mut sidecar) = app.shell().sidecar("api-server") {
        sidecar = sidecar
            .env("AUDIOTHECA_HOME", &home)
            .env("AUDIOTHECA_NO_RELOAD", "1");
        if let Some(engine_path) = &engine {
            sidecar = sidecar.env("AUDIOTHECA_ENGINE", engine_path);
        }
        if let Ok((_rx, child)) = sidecar.spawn() {
            eprintln!("[audiotheca] API sidecar started (AUDIOTHECA_HOME={home})");
            return Some(ApiProcess::Sidecar(child));
        }
    }

    for launcher in ["python", "python3", "py"] {
        let mut cmd = Command::new(launcher);
        cmd.current_dir(root);
        if launcher == "py" {
            cmd.arg("-3");
        }
        cmd.args(["-m", "api.server"]);
        cmd.stdin(Stdio::null());
        cmd.stdout(Stdio::null());
        cmd.stderr(Stdio::null());
        cmd.env("AUDIOTHECA_HOME", &home);
        cmd.env("PYTHONUNBUFFERED", "1");
        cmd.env("AUDIOTHECA_NO_RELOAD", "1");
        if let Some(engine_path) = &engine {
            cmd.env("AUDIOTHECA_ENGINE", engine_path);
        }

        if let Ok(child) = cmd.spawn() {
            eprintln!("[audiotheca] API server started via {launcher}");
            return Some(ApiProcess::Python(child));
        }
    }

    eprintln!("[audiotheca] Could not start API — build sidecars or install Python");
    None
}

fn stop_api_server(state: &ApiChild) {
    if let Ok(mut guard) = state.0.lock() {
        if let Some(process) = guard.take() {
            match process {
                ApiProcess::Sidecar(child) => {
                    let _ = child.kill();
                    eprintln!("[audiotheca] API sidecar stopped");
                }
                ApiProcess::Python(mut child) => {
                    let _ = child.kill();
                    let _ = child.wait();
                    eprintln!("[audiotheca] API server stopped");
                }
            }
        }
    }
}

#[tauri::command]
fn api_base_url() -> String {
    format!("http://127.0.0.1:{API_PORT}/api")
}

#[tauri::command]
fn workspace_path() -> String {
    workspace_root().display().to_string()
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_shell::init())
        .invoke_handler(tauri::generate_handler![api_base_url, workspace_path])
        .setup(|app| {
            let root = workspace_root();
            let child = spawn_api_server(app, &root);
            app.manage(ApiChild(Mutex::new(child)));
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app_handle, event| {
            if let RunEvent::Exit = event {
                if let Some(state) = app_handle.try_state::<ApiChild>() {
                    stop_api_server(&state);
                }
            }
        });
}
