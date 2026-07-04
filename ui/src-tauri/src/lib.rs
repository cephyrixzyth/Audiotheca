use std::net::TcpListener;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use tauri::{Manager, RunEvent, State};
use tauri_plugin_shell::process::CommandChild;
use tauri_plugin_shell::ShellExt;

const API_PORT_MIN: u16 = 8787;
const API_PORT_MAX: u16 = 8797;

enum ApiProcess {
    Sidecar(CommandChild),
    Python(Child),
}

struct ApiChild(Mutex<Option<ApiProcess>>);
struct ApiPort(Mutex<u16>);

fn portable_home_from_config(exe_dir: &Path) -> Option<PathBuf> {
    let config_path = exe_dir.join("portable.json");
    let raw = std::fs::read_to_string(&config_path).ok()?;
    let value: serde_json::Value = serde_json::from_str(&raw).ok()?;
    if value.get("relative_to_exe").and_then(|v| v.as_bool()) != Some(true) {
        return None;
    }
    let home_rel = value.get("audiotheca_home").and_then(|v| v.as_str()).unwrap_or("data");
    Some(exe_dir.join(home_rel))
}

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
        if let Some(exe_dir) = exe.parent() {
            if let Some(portable) = portable_home_from_config(exe_dir) {
                return portable;
            }
            return exe_dir.to_path_buf();
        }
        PathBuf::from(".")
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

fn free_port_listeners(port: u16) {
    #[cfg(windows)]
    {
        let script = format!(
            "Get-NetTCPConnection -LocalPort {port} -ErrorAction SilentlyContinue | \
             Select-Object -ExpandProperty OwningProcess -Unique | \
             ForEach-Object {{ Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }}"
        );
        let _ = Command::new("powershell")
            .args([
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                &script,
            ])
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status();
    }
}

fn can_bind(port: u16) -> bool {
    TcpListener::bind(("127.0.0.1", port)).is_ok()
}

fn pick_api_port() -> u16 {
    for port in API_PORT_MIN..=API_PORT_MAX {
        free_port_listeners(port);
        if can_bind(port) {
            if port != API_PORT_MIN {
                eprintln!("[audiotheca] Port {API_PORT_MIN} busy — using {port} for API");
            }
            return port;
        }
    }
    eprintln!("[audiotheca] Warning: no free API port in {API_PORT_MIN}-{API_PORT_MAX}; defaulting to {API_PORT_MIN}");
    API_PORT_MIN
}

fn spawn_api_server(app: &tauri::App, root: &Path, port: u16) -> Option<ApiProcess> {
    let port_str = port.to_string();
    let (home, engine) = sidecar_env(app, root);

    if let Ok(mut sidecar) = app.shell().sidecar("api-server") {
        sidecar = sidecar
            .env("AUDIOTHECA_HOME", &home)
            .env("AUDIOTHECA_NO_RELOAD", "1")
            .env("AUDIOTHECA_API_PORT", &port_str);
        if let Some(engine_path) = &engine {
            sidecar = sidecar.env("AUDIOTHECA_ENGINE", engine_path);
        }
        if let Ok((_rx, child)) = sidecar.spawn() {
            eprintln!("[audiotheca] API sidecar started on port {port} (AUDIOTHECA_HOME={home})");
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
        cmd.env("AUDIOTHECA_API_PORT", &port_str);
        if let Some(engine_path) = &engine {
            cmd.env("AUDIOTHECA_ENGINE", engine_path);
        }

        if let Ok(child) = cmd.spawn() {
            eprintln!("[audiotheca] API server started via {launcher} on port {port}");
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
fn api_base_url(port: State<ApiPort>) -> String {
    let api_port = *port.0.lock().unwrap_or_else(|e| e.into_inner());
    format!("http://127.0.0.1:{api_port}/api")
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
            let api_port = pick_api_port();
            app.manage(ApiPort(Mutex::new(api_port)));
            let child = spawn_api_server(app, &root, api_port);
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
