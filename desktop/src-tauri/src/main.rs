#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde::Serialize;
use std::fs;
use std::io::{Read, Write};
use std::net::{SocketAddr, TcpStream};
use std::path::PathBuf;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};
use tauri::menu::{Menu, MenuItem};
use tauri::tray::TrayIconBuilder;
use tauri::{Manager, WebviewUrl, WebviewWindowBuilder, WindowEvent};
use tauri_plugin_autostart::{MacosLauncher, ManagerExt};
use tauri_plugin_shell::process::CommandChild;
use tauri_plugin_shell::ShellExt;

#[derive(Default)]
struct RuntimeState {
    child: Option<CommandChild>,
    starting: bool,
    failed: bool,
    ready: bool,
    message: String,
    keep_running: bool,
    autostart: bool,
    data_dir: PathBuf,
    status_url: Option<tauri::Url>,
}

fn save_preferences(state: &RuntimeState) -> Result<(), String> {
    let path = state.data_dir.join("desktop-preferences.json");
    let value = serde_json::json!({
        "keep_running": state.keep_running,
        "autostart": state.autostart,
    });
    fs::write(path, value.to_string()).map_err(|e| e.to_string())
}

type Shared = Arc<Mutex<RuntimeState>>;

#[derive(Serialize)]
struct DesktopStatus {
    message: String,
    failed: bool,
    ready: bool,
    autostart: bool,
    keep_running: bool,
}

#[tauri::command]
fn desktop_status(state: tauri::State<Shared>) -> DesktopStatus {
    let guard = state.lock().unwrap();
    DesktopStatus {
        message: guard.message.clone(),
        failed: guard.failed,
        ready: guard.ready,
        autostart: guard.autostart,
        keep_running: guard.keep_running,
    }
}

#[tauri::command]
fn set_autostart(app: tauri::AppHandle, state: tauri::State<Shared>, enabled: bool) -> Result<(), String> {
    if enabled {
        app.autolaunch().enable().map_err(|e| e.to_string())?;
    } else {
        app.autolaunch().disable().map_err(|e| e.to_string())?;
    }
    let mut guard = state.lock().unwrap();
    guard.autostart = enabled;
    save_preferences(&guard)?;
    Ok(())
}

#[tauri::command]
fn set_keep_running(state: tauri::State<Shared>, enabled: bool) -> Result<(), String> {
    let mut guard = state.lock().unwrap();
    guard.keep_running = enabled;
    save_preferences(&guard)?;
    Ok(())
}

#[tauri::command]
fn retry_backend(app: tauri::AppHandle, state: tauri::State<Shared>) {
    if let Some(child) = state.lock().unwrap().child.take() {
        let _ = child.kill();
    }
    launch_backend(app, state.inner().clone());
}

#[tauri::command]
fn open_vault(app: tauri::AppHandle, state: tauri::State<Shared>) -> Result<(), String> {
    let path = state.lock().unwrap().data_dir.join("runtime.json");
    let port = configured_port(&path)?;
    let ready = http_status(port, "/ready") == Some(200);
    let target = format!("http://127.0.0.1:{port}/{}", if ready { "app" } else { "setup" });
    let window = app.get_webview_window("main").ok_or("Desktop window is unavailable")?;
    window.navigate(target.parse().map_err(|_| "The local address is invalid")?)
        .map_err(|e| e.to_string())
}

fn http_status(port: u16, path: &str) -> Option<u16> {
    let address = SocketAddr::from(([127, 0, 0, 1], port));
    let mut stream = TcpStream::connect_timeout(&address, Duration::from_millis(300)).ok()?;
    stream.set_read_timeout(Some(Duration::from_millis(500))).ok()?;
    write!(stream, "GET {path} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nConnection: close\r\n\r\n").ok()?;
    let mut bytes = [0u8; 128];
    let count = stream.read(&mut bytes).ok()?;
    let line = std::str::from_utf8(&bytes[..count]).ok()?.lines().next()?;
    line.split_whitespace().nth(1)?.parse().ok()
}

fn configured_port(path: &PathBuf) -> Result<u16, String> {
    let value: serde_json::Value = serde_json::from_slice(&fs::read(path).map_err(|e| e.to_string())?)
        .map_err(|e| e.to_string())?;
    value["port"].as_u64().and_then(|p| u16::try_from(p).ok())
        .ok_or_else(|| "The local configuration has an invalid port.".to_string())
}

fn set_message(state: &Shared, message: &str, failed: bool) {
    let mut guard = state.lock().unwrap();
    guard.message = message.to_string();
    guard.failed = failed;
    if failed { guard.ready = false; }
}

fn launch_backend(app: tauri::AppHandle, state: Shared) {
    {
        let mut guard = state.lock().unwrap();
        if guard.starting { return; }
        guard.starting = true;
        guard.failed = false;
        guard.ready = false;
        guard.message = "Starting your private vault…".into();
    }
    tauri::async_runtime::spawn(async move {
        let outcome = start_and_wait(&app, &state).await;
        if let Err(message) = outcome {
            set_message(&state, &message, true);
        }
        state.lock().unwrap().starting = false;
    });
}

fn monitor_backend(app: tauri::AppHandle, state: Shared) {
    std::thread::spawn(move || loop {
        std::thread::sleep(Duration::from_secs(5));
        let (ready, starting, data_dir, status_url) = {
            let guard = state.lock().unwrap();
            (guard.ready, guard.starting, guard.data_dir.clone(), guard.status_url.clone())
        };
        if !ready || starting { continue; }
        let available = configured_port(&data_dir.join("runtime.json"))
            .ok().and_then(|port| http_status(port, "/api/setup/status")) == Some(200);
        if !available {
            if let Some(child) = state.lock().unwrap().child.take() {
                let _ = child.kill();
            }
            set_message(&state, "The local vault stopped. Restarting…", false);
            state.lock().unwrap().ready = false;
            if let (Some(window), Some(url)) = (app.get_webview_window("main"), status_url) {
                let _ = window.navigate(url);
            }
            launch_backend(app.clone(), state.clone());
        }
    });
}

async fn start_and_wait(app: &tauri::AppHandle, state: &Shared) -> Result<(), String> {
    let data_dir = state.lock().unwrap().data_dir.clone();
    let config = data_dir.join("runtime.json");
    if !config.exists() {
        let result = app.shell().sidecar("twofauto-runtime").map_err(|e| e.to_string())?
            .args(["init", "--role", "desktop-web", "--data-dir",
                   data_dir.to_str().ok_or("The data path is not valid UTF-8")?])
            .status().await.map_err(|e| e.to_string())?;
        if !result.success() { return Err("Could not create the local vault configuration.".into()); }
    }
    let port = configured_port(&config)?;
    let address = format!("http://127.0.0.1:{port}");

    if http_status(port, "/api/setup/status").is_none() {
        let (_events, child) = app.shell().sidecar("twofauto-runtime").map_err(|e| e.to_string())?
            .args(["serve", "--config", config.to_str().ok_or("The data path is not valid UTF-8")?])
            .spawn().map_err(|e| format!("Could not start the vault: {e}"))?;
        state.lock().unwrap().child = Some(child);
    }

    let deadline = Instant::now() + Duration::from_secs(30);
    while Instant::now() < deadline {
        if http_status(port, "/api/setup/status") == Some(200) {
            let ready = http_status(port, "/ready") == Some(200);
            let target = if ready { format!("{address}/app") } else { format!("{address}/setup") };
            let url = target.parse().map_err(|_| "The local address is invalid")?;
            if let Some(window) = app.get_webview_window("main") {
                window.navigate(url).map_err(|e| e.to_string())?;
            }
            set_message(state, if ready { "Vault ready" } else { "Set up your vault" }, false);
            state.lock().unwrap().ready = true;
            return Ok(());
        }
        std::thread::sleep(Duration::from_millis(250));
    }
    Err("The local vault did not start. Check that its port is free, then try again.".into())
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _, _| {
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.show();
                let _ = window.set_focus();
            }
        }))
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_autostart::init(MacosLauncher::LaunchAgent, None))
        .invoke_handler(tauri::generate_handler![desktop_status, set_autostart, set_keep_running, retry_backend, open_vault])
        .setup(|app| {
            let data_dir = app.path().app_local_data_dir()?;
            fs::create_dir_all(&data_dir)?;
            let preferences = fs::read(data_dir.join("desktop-preferences.json"))
                .ok().and_then(|b| serde_json::from_slice::<serde_json::Value>(&b).ok())
                .unwrap_or_default();
            let keep_running = preferences["keep_running"].as_bool().unwrap_or(false);
            let autostart = preferences["autostart"].as_bool().unwrap_or(true);
            if autostart && !app.autolaunch().is_enabled().unwrap_or(false) {
                let _ = app.autolaunch().enable();
            }
            let state: Shared = Arc::new(Mutex::new(RuntimeState {
                message: "Starting your private vault…".into(),
                keep_running, autostart: app.autolaunch().is_enabled().unwrap_or(false),
                data_dir, ..RuntimeState::default()
            }));
            app.manage(state.clone());

            let show = MenuItem::with_id(app, "show", "Open 2FAuto", true, None::<&str>)?;
            let settings = MenuItem::with_id(app, "settings", "Desktop settings", true, None::<&str>)?;
            let quit = MenuItem::with_id(app, "quit", "Quit 2FAuto", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&show, &settings, &quit])?;
            TrayIconBuilder::new()
                .icon(app.default_window_icon().unwrap().clone())
                .menu(&menu)
                .on_menu_event(|app, event| match event.id().as_ref() {
                    "show" => {
                        if let Some(window) = app.get_webview_window("main") {
                            let _ = window.show();
                            let _ = window.set_focus();
                        }
                    }
                    "settings" => {
                        if let Some(window) = app.get_webview_window("main") {
                            if let Some(url) = app.state::<Shared>().lock().unwrap().status_url.clone() {
                                let _ = window.navigate(url);
                            }
                            let _ = window.show();
                            let _ = window.set_focus();
                        }
                    }
                    "quit" => app.exit(0),
                    _ => {}
                })
                .build(app)?;

            let window = WebviewWindowBuilder::new(app, "main", WebviewUrl::App("index.html".into()))
                .title("2FAuto")
                .inner_size(1000.0, 720.0)
                .build()?;
            state.lock().unwrap().status_url = window.url().ok();
            launch_backend(app.handle().clone(), state.clone());
            monitor_backend(app.handle().clone(), state);
            Ok(())
        })
        .on_window_event(|window, event| {
            if let WindowEvent::CloseRequested { api, .. } = event {
                let state = window.state::<Shared>();
                if state.lock().unwrap().keep_running {
                    api.prevent_close();
                    let _ = window.hide();
                }
            }
        })
        .build(tauri::generate_context!())
        .expect("2FAuto desktop could not start")
        .run(|app, event| {
            if let tauri::RunEvent::Exit = event {
                if let Some(state) = app.try_state::<Shared>() {
                    if let Some(child) = state.lock().unwrap().child.take() {
                        let _ = child.kill();
                    }
                }
            }
        });
}
