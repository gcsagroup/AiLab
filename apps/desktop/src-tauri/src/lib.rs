#[cfg(test)]
mod connection_scope_tests;
mod control;
mod credentials;
mod exit_preparation;
mod python_picker;
mod startup;

use base64::Engine;
use control::{Connection, ControlProcess, HostStatus, LaunchConfig};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::{
    fs,
    path::{Component, Path, PathBuf},
    sync::{
        atomic::{AtomicBool, Ordering},
        Mutex,
    },
    time::{Duration, Instant},
};
use tauri::{Emitter, Manager, State};

struct HostState {
    process: Mutex<ControlProcess>,
    launch: Mutex<LaunchConfig>,
    fallback: LaunchConfig,
    selection_file: PathBuf,
    settings_file: PathBuf,
    client: reqwest::Client,
    exiting: AtomicBool,
    exit_dialog: AtomicBool,
    exit_preparation: Mutex<exit_preparation::ExitPreparation>,
    switching: AtomicBool,
    credential_busy: AtomicBool,
    startup: Mutex<startup::StartupMetrics>,
}

#[derive(Serialize, Deserialize)]
struct LibrarySelection {
    data_dir: PathBuf,
    previous_data_dir: PathBuf,
    restore_id: String,
}

#[derive(Default, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct HostSettings {
    market_fixture_origin: Option<String>,
}

fn validate_fixture_origin(origin: Option<&str>) -> Result<(), Value> {
    let Some(origin) = origin else {
        return Ok(());
    };
    let port = origin.strip_prefix("http://127.0.0.1:").and_then(|port| {
        port.parse::<u16>()
            .ok()
            .filter(|number| *number > 0 && number.to_string() == port)
    });
    if port.is_none() {
        return Err(error(
            "MARKET_FIXTURE_ORIGIN_INVALID",
            "受控来源地址必须为 http://127.0.0.1:端口，端口范围 1 至 65535。",
        ));
    }
    Ok(())
}

fn fixture_origin(launch: &LaunchConfig) -> Option<String> {
    launch
        .args
        .windows(2)
        .find(|pair| pair[0] == "--market-fixture-origin")
        .map(|pair| pair[1].clone())
}

fn configure_launch_fixture(launch: &mut LaunchConfig, origin: Option<&str>) {
    let mut arguments = Vec::new();
    let mut source = launch.args.iter();
    while let Some(argument) = source.next() {
        if argument == "--market-fixture-origin" {
            source.next();
        } else {
            arguments.push(argument.clone());
        }
    }
    if let Some(origin) = origin {
        arguments.extend(["--market-fixture-origin".into(), origin.into()]);
    }
    launch.args = arguments;
}

fn load_host_settings(path: &Path) -> Result<HostSettings, String> {
    let metadata = match fs::symlink_metadata(path) {
        Ok(metadata) => metadata,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
            return Ok(HostSettings::default())
        }
        Err(_) => return Err("无法读取宿主连接设置。".into()),
    };
    if !metadata.is_file() || metadata.file_type().is_symlink() || metadata.len() > 4096 {
        return Err("宿主连接设置必须为有效的小型普通文件。".into());
    }
    let settings: HostSettings = fs::read(path)
        .ok()
        .and_then(|bytes| serde_json::from_slice(&bytes).ok())
        .ok_or("宿主连接设置格式无效。")?;
    validate_fixture_origin(settings.market_fixture_origin.as_deref())
        .map_err(|_| "宿主受控来源地址无效。")?;
    Ok(settings)
}

fn described_status(status: HostStatus, launch: &LaunchConfig) -> Value {
    let mut result = serde_json::to_value(status).expect("服务状态可以序列化");
    result["market_fixture_origin"] = json!(fixture_origin(launch));
    result
}

struct SwitchingGuard<'a>(&'a AtomicBool);
impl Drop for SwitchingGuard<'_> {
    fn drop(&mut self) {
        self.0.store(false, Ordering::SeqCst);
    }
}

fn reserve_host_change<'a>(
    state: &HostState,
    busy: &'a AtomicBool,
    busy_code: &str,
    busy_message: &str,
) -> Result<SwitchingGuard<'a>, Value> {
    let preparation = state
        .exit_preparation
        .lock()
        .map_err(|_| error("HOST_STATE_ERROR", "无法读取退出保存状态。"))?;
    if preparation.is_pending() || state.exiting.load(Ordering::SeqCst) {
        return Err(error(
            "EXIT_PREPARATION_PENDING",
            "正在保存退出前的草稿与当前选择，请稍候。",
        ));
    }
    if busy.swap(true, Ordering::SeqCst) {
        return Err(error(busy_code, busy_message));
    }
    let guard = SwitchingGuard(busy);
    // 先占本方门禁，再检查另一方；与凭据 Gate 的相同顺序配合，不能同时进入。
    if !std::ptr::eq(busy, &state.switching) && state.switching.load(Ordering::SeqCst) {
        return Err(error(
            "LIBRARY_SWITCH_PENDING",
            "正在切换工作库，请等待连接完成。",
        ));
    }
    if !std::ptr::eq(busy, &state.credential_busy) && state.credential_busy.load(Ordering::SeqCst) {
        return Err(error(
            "CREDENTIAL_OPERATION_PENDING",
            "正在更新连接凭据，请完成后再切换工作库。",
        ));
    }
    Ok(guard)
}

fn restored_path(path: &Path, restore_id: &str) -> Result<PathBuf, Value> {
    if !path.is_absolute()
        || path
            .components()
            .any(|part| matches!(part, Component::ParentDir))
    {
        return Err(error("RESTORE_PATH_INVALID", "恢复目录路径无效。"));
    }
    for part in path.ancestors() {
        if fs::symlink_metadata(part).map_or(true, |metadata| metadata.file_type().is_symlink()) {
            return Err(error(
                "RESTORE_PATH_INVALID",
                "恢复目录包含链接或已不存在。",
            ));
        }
    }
    for name in ["control.sqlite3", "restoration.json"] {
        if fs::symlink_metadata(path.join(name)).map_or(true, |metadata| {
            !metadata.is_file() || metadata.file_type().is_symlink()
        }) {
            return Err(error(
                "RESTORE_PATH_INVALID",
                "恢复目录缺少已核实的数据库或回执。",
            ));
        }
    }
    let receipt: Value = fs::read(path.join("restoration.json"))
        .ok()
        .and_then(|value| serde_json::from_slice(&value).ok())
        .ok_or_else(|| error("RESTORE_PATH_INVALID", "恢复回执无效。"))?;
    if receipt.get("restore_id").and_then(Value::as_str) != Some(restore_id) {
        return Err(error(
            "RESTORE_PATH_INVALID",
            "恢复目录与已选择的记录不匹配。",
        ));
    }
    path.canonicalize()
        .map_err(|_| error("RESTORE_PATH_INVALID", "恢复目录不可访问。"))
}

#[derive(Deserialize)]
pub struct ApiRequest {
    method: String,
    path: String,
    body: Option<Value>,
    idempotency_key: Option<String>,
}

#[derive(Deserialize)]
struct BridgeApiRequest {
    #[serde(flatten)]
    request: ApiRequest,
    connection_id: String,
}

fn error(code: &str, message: &str) -> Value {
    json!({"error":{"code":code,"message":message,"details":{}}})
}

fn validate_request(request: &ApiRequest) -> Result<(), Value> {
    if !matches!(
        request.method.as_str(),
        "GET" | "POST" | "PATCH" | "PUT" | "DELETE"
    ) {
        return Err(error("HOST_REQUEST_DENIED", "此请求方法不受支持。"));
    }
    if request.path.len() > 4096
        || !request.path.is_ascii()
        || request.path.contains(['#', '\\', '\r', '\n'])
    {
        return Err(error("HOST_REQUEST_DENIED", "请求路径无效。"));
    }
    let path = request.path.split('?').next().unwrap_or("");
    let Some(relative) = path.strip_prefix("/api/v1/") else {
        return Err(error("HOST_REQUEST_DENIED", "只允许访问本机应用接口。"));
    };
    let segments: Vec<_> = relative.split('/').collect();
    if segments.iter().any(|segment| {
        segment.is_empty()
            || *segment == "."
            || *segment == ".."
            || !segment
                .bytes()
                .all(|byte| byte.is_ascii_alphanumeric() || b"_- .".contains(&byte))
            || segment.contains(' ')
    }) {
        return Err(error("HOST_REQUEST_DENIED", "请求路径包含不允许的内容。"));
    }
    if !matches!(
        segments[0],
        "projects"
            | "ai"
            | "models"
            | "model-catalog"
            | "model-downloads"
            | "execution-targets"
            | "remote-transfers"
            | "datasets"
            | "materials"
            | "market"
            | "training-contracts"
            | "artifacts"
            | "adapters"
            | "collections"
            | "checkpoints"
            | "cleanup-plans"
            | "cleanups"
            | "conversions"
            | "evaluation-plans"
            | "candidates"
            | "devices"
            | "diagnostics"
            | "capabilities"
            | "tasks"
            | "attempts"
            | "works"
            | "settings"
            | "ui-context"
            | "environments"
            | "exports"
            | "backups"
            | "restore-plans"
            | "restores"
            | "workflow-runs"
            | "evaluations"
            | "recipes"
            | "health"
    ) {
        return Err(error("HOST_REQUEST_DENIED", "此应用接口未获授权。"));
    }
    if segments[0] == "ui-context"
        && (!matches!(request.method.as_str(), "GET" | "PATCH")
            || request.path != "/api/v1/ui-context")
    {
        return Err(error(
            "HOST_REQUEST_DENIED",
            "当前选择只允许通过固定接口读取或保存。",
        ));
    }
    if segments[0] == "training-contracts"
        && !matches!(
            (request.method.as_str(), segments.as_slice()),
            ("GET", ["training-contracts"])
        )
    {
        return Err(error("HOST_REQUEST_DENIED", "训练合同只允许读取静态配置。"));
    }
    if segments[0] == "execution-targets" {
        let allowed = match (request.method.as_str(), segments.as_slice()) {
            ("GET", ["execution-targets"]) => true,
            ("GET", ["execution-targets", id]) => credentials::valid_target(id),
            ("POST", ["execution-targets", id, "check"]) => {
                credentials::valid_target(id)
                    && request
                        .body
                        .as_ref()
                        .is_some_and(|body| body.as_object().is_some_and(|body| body.is_empty()))
            }
            _ => false,
        };
        if !allowed {
            return Err(error(
                "HOST_REQUEST_DENIED",
                "远端连接凭据只能通过原生连接操作管理。",
            ));
        }
    }
    if segments[0] == "remote-transfers"
        && !matches!(
            (request.method.as_str(), segments.as_slice()),
            ("GET" | "POST", ["remote-transfers"]) | ("POST", ["remote-transfers", "prepare"])
        )
    {
        return Err(error("HOST_REQUEST_DENIED", "此回环文件传输操作未获授权。"));
    }
    if segments[0] == "ai"
        && !matches!(
            (request.method.as_str(), segments.as_slice()),
            ("GET" | "POST", ["ai", "requests"])
                | ("GET", ["ai", "requests", _])
                | ("POST", ["ai", "requests", _, "proposals"])
                | ("GET", ["ai", "proposals", _])
                | ("POST", ["ai", "proposals", _, "apply" | "undo"])
        )
    {
        return Err(error("HOST_REQUEST_DENIED", "此 AI 建议操作未获授权。"));
    }
    if segments[0] == "market"
        && !matches!(
            (request.method.as_str(), segments.as_slice()),
            ("GET", ["market", "sources" | "catalog" | "local-versions"])
                | ("GET", ["market", "versions", _, "activity"])
                | ("POST", ["market", "access-requests" | "downloads"])
                | ("POST", ["market", "access-requests", _, "refresh"])
                | ("GET", ["market", "downloads", _])
                | (
                    "POST",
                    ["market", "downloads", _, "cancel" | "resume" | "datasets"]
                )
                | ("POST", ["market", "contexts", _, "use"])
        )
    {
        return Err(error("HOST_REQUEST_DENIED", "此受控来源操作未获授权。"));
    }
    if matches!(segments[0], "model-catalog" | "model-downloads") {
        let valid_id = |id: &str| {
            id.strip_prefix("model-download-").is_some_and(|suffix| {
                suffix.len() == 32
                    && suffix
                        .bytes()
                        .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
            })
        };
        let allowed = match (request.method.as_str(), segments.as_slice()) {
            ("GET", ["model-catalog"]) | ("GET" | "POST", ["model-downloads"]) => true,
            ("GET", ["model-downloads", id])
            | ("POST", ["model-downloads", id, "resume" | "cancel" | "models"]) => valid_id(id),
            _ => false,
        };
        if !allowed {
            return Err(error("HOST_REQUEST_DENIED", "此固定模型下载操作未获授权。"));
        }
    }
    if segments[0] == "diagnostics" {
        let valid_id = |id: &str| {
            id.strip_prefix("diagnostic-preview-")
                .is_some_and(|suffix| {
                    suffix.len() == 32
                        && suffix
                            .bytes()
                            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
                })
        };
        let allowed = match (request.method.as_str(), segments.as_slice()) {
            ("POST", ["diagnostics", "previews" | "exports"]) => true,
            ("GET", ["diagnostics", "previews", id])
            | ("POST", ["diagnostics", "previews", id, "cancel"]) => valid_id(id),
            _ => false,
        };
        if !allowed {
            return Err(error(
                "HOST_REQUEST_DENIED",
                "此诊断预览或导出操作未获授权。",
            ));
        }
    }
    if segments[0] == "settings" && request.method != "GET" {
        return Err(error(
            "HOST_REQUEST_DENIED",
            "执行环境只能通过原生选择器明确设置。",
        ));
    }
    if segments[0] == "restores" && segments.get(2) == Some(&"activation") {
        return Err(error(
            "HOST_REQUEST_DENIED",
            "切换工作库必须通过原生宿主操作。",
        ));
    }
    if request.method == "GET" && request.body.is_some() {
        return Err(error("HOST_REQUEST_DENIED", "读取请求不能包含正文。"));
    }
    if request
        .body
        .as_ref()
        .is_some_and(|body| body.to_string().len() > 1024 * 1024)
    {
        return Err(error(
            "HOST_REQUEST_TOO_LARGE",
            "请求内容超过 1 MB，请通过文件导入。",
        ));
    }
    if request.idempotency_key.as_ref().is_some_and(|key| {
        key.is_empty() || key.len() > 128 || !key.bytes().all(|byte| byte.is_ascii_graphic())
    }) {
        return Err(error("HOST_REQUEST_DENIED", "请求编号无效。"));
    }
    Ok(())
}

async fn proxy(state: &HostState, request: ApiRequest) -> Result<Value, Value> {
    proxy_internal(state, request, false).await
}

async fn proxy_host(state: &HostState, request: ApiRequest) -> Result<Value, Value> {
    proxy_internal(state, request, true).await
}

async fn proxy_internal(
    state: &HostState,
    request: ApiRequest,
    host_only: bool,
) -> Result<Value, Value> {
    let connection = state
        .process
        .lock()
        .map_err(|_| error("HOST_STATE_ERROR", "无法读取本地服务状态。"))?
        .connection()
        .ok_or_else(|| error("CONTROL_UNAVAILABLE", "本地服务未连接，请重启服务。"))?;
    proxy_connection(state, request, host_only, connection).await
}

async fn proxy_connection(
    state: &HostState,
    request: ApiRequest,
    host_only: bool,
    connection: Connection,
) -> Result<Value, Value> {
    // 主机、端口和认证由 Rust 持有；关闭重定向，令牌不会跟随外部地址。
    let url = format!("http://127.0.0.1:{}{}", connection.port, request.path);
    let method = reqwest::Method::from_bytes(request.method.as_bytes())
        .map_err(|_| error("HOST_REQUEST_DENIED", "请求方法无效。"))?;
    let mut builder = state
        .client
        .request(method, url)
        .bearer_auth(connection.token);
    if host_only {
        let token = connection.host_token.ok_or_else(|| {
            error(
                "HOST_AUTH_REQUIRED",
                "本地控制服务未提供宿主专属身份，请重启应用。",
            )
        })?;
        builder = builder.header("X-AiLab-Host-Token", token);
        if request.method == "DELETE" {
            builder = builder.timeout(Duration::from_secs(10));
        }
    }
    if let Some(body) = request.body {
        builder = builder.json(&body);
    }
    if let Some(key) = request.idempotency_key {
        builder = builder.header("Idempotency-Key", key);
    }
    let mut response = builder.send().await.map_err(|_| {
        error(
            "CONTROL_UNAVAILABLE",
            "无法连接本地服务，请查看服务状态或重启服务。",
        )
    })?;
    let successful = response.status().is_success();
    let mut bytes = Vec::new();
    while let Some(chunk) = response
        .chunk()
        .await
        .map_err(|_| error("CONTROL_RESPONSE_INVALID", "读取本地服务结果失败。"))?
    {
        if bytes.len() + chunk.len() > 8 * 1024 * 1024 {
            return Err(error(
                "CONTROL_RESPONSE_TOO_LARGE",
                "结果过大，请分页读取。",
            ));
        }
        bytes.extend_from_slice(&chunk);
    }
    let value = if bytes.is_empty() && successful {
        Value::Null
    } else {
        serde_json::from_slice(&bytes)
            .map_err(|_| error("CONTROL_RESPONSE_INVALID", "本地服务返回了无法识别的结果。"))?
    };
    if successful {
        Ok(value)
    } else if value.get("error").is_some() {
        Err(value)
    } else {
        Err(error(
            "CONTROL_REQUEST_FAILED",
            "本地请求失败，请重试或查看日志。",
        ))
    }
}

#[tauri::command]
async fn api_request(
    request: BridgeApiRequest,
    state: State<'_, HostState>,
) -> Result<Value, Value> {
    bridge_request(&state, request).await
}

async fn bridge_request(state: &HostState, request: BridgeApiRequest) -> Result<Value, Value> {
    validate_request(&request.request)?;
    let connection = bridge_connection(state, &request.connection_id)?;
    let result = proxy_connection(state, request.request, false, connection).await;
    complete_bridge_request(state, &request.connection_id, result)
}

fn bridge_connection(state: &HostState, connection_id: &str) -> Result<Connection, Value> {
    // 在进程锁内核对前端捕获的连接身份；排队到切换结束的旧 IPC 也必须拒绝。
    let mut process = state
        .process
        .lock()
        .map_err(|_| error("HOST_STATE_ERROR", "无法读取本地服务状态。"))?;
    if state.switching.load(Ordering::SeqCst) {
        return Err(error(
            "LIBRARY_SWITCH_PENDING",
            "正在切换工作库，请等待连接完成。",
        ));
    }
    process
        .connection()
        .filter(|connection| connection.connection_id == connection_id)
        .ok_or_else(|| {
            error(
                "CONTROL_CONNECTION_CHANGED",
                "工作库连接已变化，请重新读取后再操作。",
            )
        })
}

fn complete_bridge_request<T>(
    state: &HostState,
    connection_id: &str,
    result: Result<T, Value>,
) -> Result<T, Value> {
    // 成功和失败都要复核，旧服务结果不能成为新工作库的状态或错误提示。
    bridge_connection(state, connection_id)?;
    result
}

fn media_path(artifact_id: &str) -> Result<String, Value> {
    let valid = artifact_id.strip_prefix("artifact-").is_some_and(|value| {
        value.len() == 32
            && value
                .bytes()
                .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
    });
    if !valid {
        return Err(error("MEDIA_REQUEST_DENIED", "请选择已保存的媒体产物。"));
    }
    Ok(format!("/api/v1/artifacts/{artifact_id}/content"))
}

async fn media_response(mut response: reqwest::Response, maximum: usize) -> Result<Value, Value> {
    let successful = response.status().is_success();
    let media_type = response
        .headers()
        .get(reqwest::header::CONTENT_TYPE)
        .and_then(|value| value.to_str().ok())
        .unwrap_or("")
        .to_owned();
    if successful && !matches!(media_type.as_str(), "image/png" | "video/mp4" | "audio/wav") {
        return Err(error(
            "MEDIA_RESPONSE_INVALID",
            "产物类型不支持在应用内预览。",
        ));
    }
    let limit = if successful { maximum } else { 64 * 1024 };
    if response
        .content_length()
        .is_some_and(|length| length > limit as u64)
    {
        return Err(error(
            "MEDIA_RESPONSE_TOO_LARGE",
            "媒体超过预览大小限制，请导出后查看。",
        ));
    }
    let mut bytes = Vec::new();
    while let Some(chunk) = response
        .chunk()
        .await
        .map_err(|_| error("MEDIA_RESPONSE_INVALID", "媒体读取中断，请重新查看。"))?
    {
        if bytes.len() + chunk.len() > limit {
            return Err(error(
                "MEDIA_RESPONSE_TOO_LARGE",
                "媒体超过预览大小限制，请导出后查看。",
            ));
        }
        bytes.extend_from_slice(&chunk);
    }
    if !successful {
        if let Ok(value) = serde_json::from_slice::<Value>(&bytes) {
            if value.get("error").is_some() {
                return Err(value);
            }
        }
        return Err(error(
            "MEDIA_REQUEST_FAILED",
            "媒体读取失败，请核实原产物。",
        ));
    }
    if bytes.is_empty() {
        return Err(error("MEDIA_RESPONSE_INVALID", "媒体产物为空，无法预览。"));
    }
    Ok(
        json!({"media_type":media_type,"base64":base64::engine::general_purpose::STANDARD.encode(bytes)}),
    )
}

#[tauri::command]
async fn api_media(
    artifact_id: String,
    connection_id: String,
    state: State<'_, HostState>,
) -> Result<Value, Value> {
    bridge_media(&state, artifact_id, connection_id).await
}

async fn bridge_media(
    state: &HostState,
    artifact_id: String,
    connection_id: String,
) -> Result<Value, Value> {
    let path = media_path(&artifact_id)?;
    let connection = bridge_connection(state, &connection_id)?;
    let result = async {
        let response = state
            .client
            .get(format!("http://127.0.0.1:{}{}", connection.port, path))
            .bearer_auth(connection.token)
            .send()
            .await
            .map_err(|_| error("CONTROL_UNAVAILABLE", "媒体读取失败，请检查本地服务。"))?;
        media_response(response, 64 * 1024 * 1024).await
    }
    .await;
    complete_bridge_request(state, &connection_id, result)
}

#[tauri::command]
fn host_status(state: State<'_, HostState>) -> Result<Value, Value> {
    let launch = state
        .launch
        .lock()
        .map_err(|_| error("HOST_STATE_ERROR", "无法读取宿主设置。"))?;
    Ok(described_status(
        state
            .process
            .lock()
            .map_err(|_| error("HOST_STATE_ERROR", "无法读取本地服务状态。"))?
            .status(),
        &launch,
    ))
}

#[tauri::command]
fn record_first_frame(
    app: tauri::AppHandle,
    state: State<'_, HostState>,
    view: startup::FirstView,
    frontend: Option<startup::FrontendPhases>,
) -> Result<startup::StartupReceipt, Value> {
    let visible = app.get_webview_window("main").is_some_and(|window| {
        window.is_visible().unwrap_or(false) && !window.is_minimized().unwrap_or(true)
    });
    if !visible {
        return Err(error("FIRST_FRAME_NOT_VISIBLE", "首屏窗口尚未显示。"));
    }
    let status = state
        .process
        .lock()
        .map_err(|_| error("HOST_STATE_ERROR", "无法读取本地服务状态。"))?
        .status();
    if status.state != "running" {
        return Err(error(
            "CONTROL_UNAVAILABLE",
            "本地服务尚未连接，不能记录就绪首屏。",
        ));
    }
    state
        .startup
        .lock()
        .map_err(|_| error("HOST_STATE_ERROR", "无法读取首屏计时状态。"))?
        .record_with_phases(
            view,
            status
                .pid
                .ok_or_else(|| error("CONTROL_UNAVAILABLE", "缺少本地服务进程身份。"))?,
            frontend,
        )
        .map_err(|message| error("FIRST_FRAME_RECORD_FAILED", &message))
}

#[tauri::command]
async fn restart_control(app: tauri::AppHandle) -> Result<Value, Value> {
    tauri::async_runtime::spawn_blocking(move || {
        let state = app.state::<HostState>();
        let _credential_guard = reserve_host_change(
            &state,
            &state.credential_busy,
            "CREDENTIAL_OPERATION_PENDING",
            "正在更新连接凭据，请完成后再重启服务。",
        )?;
        let mut launch = state
            .launch
            .lock()
            .map_err(|_| error("HOST_STATE_ERROR", "无法读取工作库设置。"))?;
        let mut process = state
            .process
            .lock()
            .map_err(|_| error("HOST_STATE_ERROR", "无法重启本地服务。"))?;
        let mut result = process
            .start(&launch)
            .map_err(|message| error("CONTROL_START_FAILED", &message));
        if result.is_err() && launch.data_dir != state.fallback.data_dir {
            process.stop();
            let mut fallback = state.fallback.clone();
            configure_launch_fixture(&mut fallback, fixture_origin(&launch).as_deref());
            result = process
                .start(&fallback)
                .map_err(|message| error("CONTROL_START_FAILED", &message));
            if result.is_ok() {
                *launch = fallback;
            }
        }
        if let Ok(status) = &result {
            if let Some(pid) = status.pid {
                if let Ok(mut startup) = state.startup.lock() {
                    startup.mark_control_ready(pid);
                }
            }
        }
        let result = result.map(|status| described_status(status, &launch));
        if let Ok(status) = &result {
            let _ = app.emit("host-status", status);
        }
        result
    })
    .await
    .map_err(|_| error("CONTROL_START_FAILED", "本地服务重启失败。"))?
}

#[tauri::command]
async fn use_restored_library(restore_id: String, app: tauri::AppHandle) -> Result<Value, Value> {
    if restore_id.len() != 40
        || !restore_id.starts_with("restore-")
        || !restore_id[8..].bytes().all(|byte| byte.is_ascii_hexdigit())
    {
        return Err(error("RESTORE_NOT_FOUND", "恢复记录编号无效。"));
    }
    let state = app.state::<HostState>();
    let _guard = reserve_host_change(
        &state,
        &state.switching,
        "LIBRARY_SWITCH_PENDING",
        "正在切换工作库，请稍候。",
    )?;
    let verified = proxy(
        &state,
        ApiRequest {
            method: "GET".into(),
            path: format!("/api/v1/restores/{restore_id}"),
            body: None,
            idempotency_key: None,
        },
    )
    .await?;
    if verified.get("verified").and_then(Value::as_bool) != Some(true) {
        return Err(error("RESTORE_INCOMPLETE", "恢复文件尚未通过现场核实。"));
    }
    let selected = verified
        .get("restored_path")
        .and_then(Value::as_str)
        .ok_or_else(|| error("RESTORE_PATH_INVALID", "恢复记录没有有效目录。"))?;
    let selected = restored_path(Path::new(selected), &restore_id)?;
    let activation_result = proxy_host(
        &state,
        ApiRequest {
            method: "POST".into(),
            path: format!("/api/v1/restores/{restore_id}/activation"),
            body: Some(json!({})),
            idempotency_key: None,
        },
    )
    .await;
    if !activation_result
        .as_ref()
        .is_ok_and(|value| value.get("activation_ready").and_then(Value::as_bool) == Some(true))
    {
        // 结果不确定时先撤销门禁；控制层还会在租期结束后自动解除。
        let _ = proxy_host(
            &state,
            ApiRequest {
                method: "DELETE".into(),
                path: format!("/api/v1/restores/{restore_id}/activation"),
                body: None,
                idempotency_key: None,
            },
        )
        .await;
        return Err(activation_result
            .err()
            .unwrap_or_else(|| error("LIBRARY_BUSY", "当前工作库尚未准备好切换。")));
    }
    let handle = app.clone();
    tauri::async_runtime::spawn_blocking(move || {
        let state = handle.state::<HostState>();
        let mut launch = state
            .launch
            .lock()
            .map_err(|_| error("HOST_STATE_ERROR", "无法保存工作库设置。"))?;
        let current = launch.clone();
        let mut next = current.clone();
        next.data_dir = selected.clone();
        let selection = LibrarySelection {
            data_dir: selected.clone(),
            previous_data_dir: current.data_dir.clone(),
            restore_id,
        };
        let contents = serde_json::to_vec(&selection)
            .map_err(|_| error("HOST_STATE_ERROR", "无法保存工作库身份。"))?;
        let mut process = state
            .process
            .lock()
            .map_err(|_| error("HOST_STATE_ERROR", "无法切换本地服务。"))?;
        let result = process.switch_library(&current, &next, &state.selection_file, &contents);
        if result.is_ok() {
            *launch = next;
        }
        let status = described_status(process.status(), &launch);
        let _ = handle.emit("host-status", &status);
        result
            .map(|_| json!({"library_changed":true,"data_dir":selected,"status":status}))
            .map_err(|message| error("LIBRARY_SWITCH_FAILED", &message))
    })
    .await
    .map_err(|_| error("LIBRARY_SWITCH_FAILED", "切换工作库失败，请重新连接。"))?
}

#[tauri::command]
async fn configure_market_fixture(
    origin: Option<String>,
    app: tauri::AppHandle,
) -> Result<Value, Value> {
    validate_fixture_origin(origin.as_deref())?;
    let state = app.state::<HostState>();
    let _guard = reserve_host_change(
        &state,
        &state.switching,
        "LIBRARY_SWITCH_PENDING",
        "正在更新宿主连接，请稍候。",
    )?;
    {
        let launch = state
            .launch
            .lock()
            .map_err(|_| error("HOST_STATE_ERROR", "无法读取宿主设置。"))?;
        if fixture_origin(&launch) == origin {
            let status = state
                .process
                .lock()
                .map_err(|_| error("HOST_STATE_ERROR", "无法读取本地服务状态。"))?
                .status();
            return Ok(
                json!({"market_fixture_origin":origin,"status":described_status(status, &launch)}),
            );
        }
    }
    let gate = proxy_host(
        &state,
        ApiRequest {
            method: "POST".into(),
            path: "/api/v1/host/reconfiguration".into(),
            body: Some(json!({})),
            idempotency_key: None,
        },
    )
    .await;
    if !gate
        .as_ref()
        .is_ok_and(|value| value.get("ready").and_then(Value::as_bool) == Some(true))
    {
        let _ = proxy_host(
            &state,
            ApiRequest {
                method: "DELETE".into(),
                path: "/api/v1/host/reconfiguration".into(),
                body: Some(json!({})),
                idempotency_key: None,
            },
        )
        .await;
        return Err(gate.err().unwrap_or_else(|| {
            error(
                "LIBRARY_BUSY",
                "当前工作库有进行中的操作，请结束后再更新来源连接。",
            )
        }));
    }
    let handle = app.clone();
    let result = tauri::async_runtime::spawn_blocking(move || {
        let state = handle.state::<HostState>();
        let mut launch = state
            .launch
            .lock()
            .map_err(|_| error("HOST_STATE_ERROR", "无法读取宿主连接设置。"))?;
        let current = launch.clone();
        let mut next = current.clone();
        configure_launch_fixture(&mut next, origin.as_deref());
        let contents = serde_json::to_vec(&HostSettings {
            market_fixture_origin: origin.clone(),
        })
        .map_err(|_| error("HOST_STATE_ERROR", "无法保存宿主连接设置。"))?;
        let mut process = state
            .process
            .lock()
            .map_err(|_| error("HOST_STATE_ERROR", "无法更新宿主连接。"))?;
        let switched = process.switch_library(&current, &next, &state.settings_file, &contents);
        if switched.is_ok() {
            *launch = next;
        }
        let status = described_status(process.status(), &launch);
        let _ = handle.emit("host-status", &status);
        switched
            .map(|_| json!({"market_fixture_origin":origin,"status":status}))
            .map_err(|message| error("HOST_CONFIGURATION_FAILED", &message))
    })
    .await
    .map_err(|_| {
        error(
            "HOST_CONFIGURATION_FAILED",
            "更新宿主连接失败，请重新连接。",
        )
    })?;
    if result.is_err() {
        let _ = proxy_host(
            &state,
            ApiRequest {
                method: "DELETE".into(),
                path: "/api/v1/host/reconfiguration".into(),
                body: Some(json!({})),
                idempotency_key: None,
            },
        )
        .await;
    }
    result
}

#[derive(Serialize)]
struct ImportSelection {
    path: String,
    grant_id: String,
}

#[tauri::command]
async fn pick_import_path(
    kind: String,
    connection_id: String,
    app: tauri::AppHandle,
) -> Result<Option<ImportSelection>, Value> {
    if !matches!(
        kind.as_str(),
        "model" | "dataset" | "image-dataset" | "material" | "backup"
    ) {
        return Err(error(
            "INVALID_CONFIG",
            "请选择模型、数据集、PNG 素材或备份。",
        ));
    }
    let state = app.state::<HostState>();
    select_path_grant(&state, &connection_id, false, async move {
        let selected = tauri::async_runtime::spawn_blocking(move || {
            let dialog = rfd::FileDialog::new();
            if kind == "model" {
                dialog.set_title("选择要导入的本地模型目录").pick_folder()
            } else if kind == "backup" {
                dialog.set_title("选择完整 AI Lab 备份目录").pick_folder()
            } else if kind == "image-dataset" {
                dialog
                    .set_title("选择包含 dataset.json 和图片的数据目录")
                    .pick_folder()
            } else if kind == "material" {
                dialog
                    .set_title("选择 PNG 图片素材")
                    .add_filter("PNG 图片", &["png"])
                    .pick_file()
            } else {
                dialog
                    .set_title("选择要导入的数据集文件")
                    .add_filter("数据集", &["json", "jsonl", "csv", "txt"])
                    .pick_file()
            }
        })
        .await
        .map_err(|_| error("FILE_DIALOG_FAILED", "无法打开文件选择窗口。"))?;
        Ok(selected)
    })
    .await
}

#[tauri::command]
async fn pick_export_directory(
    connection_id: String,
    app: tauri::AppHandle,
) -> Result<Option<ImportSelection>, Value> {
    let state = app.state::<HostState>();
    select_path_grant(&state, &connection_id, true, async move {
        let selected = tauri::async_runtime::spawn_blocking(|| {
            rfd::FileDialog::new()
                .set_title("选择文件的保存目录")
                .pick_folder()
        })
        .await
        .map_err(|_| error("FILE_DIALOG_FAILED", "无法打开保存目录选择窗口。"))?;
        Ok(selected)
    })
    .await
}

async fn select_path_grant<F>(
    state: &HostState,
    connection_id: &str,
    export: bool,
    selection: F,
) -> Result<Option<ImportSelection>, Value>
where
    F: std::future::Future<Output = Result<Option<PathBuf>, Value>>,
{
    // 选择 Future 必须惰性创建原生窗口，身份校验先于首次轮询。
    let connection = bridge_connection(state, connection_id)?;
    let selected = complete_bridge_request(state, connection_id, selection.await)?;
    let result = async {
        let Some(selected) = selected else {
            return Ok(None);
        };
        let (endpoint, path_code, grant_code) = if export {
            (
                "/api/v1/export-grants",
                "EXPORT_PATH_INVALID",
                "EXPORT_GRANT_FAILED",
            )
        } else {
            (
                "/api/v1/import-grants",
                "IMPORT_PATH_INVALID",
                "IMPORT_GRANT_FAILED",
            )
        };
        let canonical = selected
            .canonicalize()
            .map_err(|_| error(path_code, "所选路径已不存在或不可访问。"))?;
        if export && !canonical.is_dir() {
            return Err(error(path_code, "请选择已有目录。"));
        }
        let path = canonical.to_string_lossy().to_string();
        // 授权只能由原生选择器产生，api_request 无法调用此接口。
        let granted = native_connection_request(
            state,
            &connection,
            ApiRequest {
                method: "POST".into(),
                path: endpoint.into(),
                body: Some(json!({"path":path})),
                idempotency_key: None,
            },
        )
        .await?;
        let grant_id = granted
            .get("grant_id")
            .and_then(Value::as_str)
            .ok_or_else(|| error(grant_code, "所选路径未获授权。"))?
            .to_string();
        Ok(Some(ImportSelection { path, grant_id }))
    }
    .await;
    complete_bridge_request(state, connection_id, result)
}

#[tauri::command]
async fn pick_worker_python(
    connection_id: String,
    app: tauri::AppHandle,
) -> Result<Option<Value>, Value> {
    select_python(app, connection_id, "worker_python", "文本生成与训练").await
}

fn media_environment_field(engine: &str) -> Result<(&'static str, &'static str), Value> {
    match engine {
        "diffusers" => Ok(("media_python", "图片与视频")),
        "kokoro" => Ok(("audio_python", "中文配音")),
        _ => Err(error(
            "ENVIRONMENT_INVALID",
            "请选择图片与视频或中文配音环境。",
        )),
    }
}

#[tauri::command]
async fn pick_media_python(
    engine: String,
    connection_id: String,
    app: tauri::AppHandle,
) -> Result<Option<Value>, Value> {
    let (field, label) = media_environment_field(&engine)?;
    select_python(app, connection_id, field, label).await
}

async fn select_python(
    app: tauri::AppHandle,
    connection_id: String,
    field: &'static str,
    label: &'static str,
) -> Result<Option<Value>, Value> {
    let handle = app.clone();
    let state = handle.state::<HostState>();
    select_python_environment(&state, &connection_id, field, async move {
        let window = app
            .get_webview_window("main")
            .ok_or_else(|| error("WINDOW_UNAVAILABLE", "应用窗口不可用。"))?;
        let selected = tauri::async_runtime::spawn_blocking(move || {
            let Some(path) = python_picker::pick_file(
                &app,
                format!("选择已准备的{label} Python 环境"),
            )? else {
                return Ok(None);
            };
            let description = format!(
                "应用将使用下列程序执行本机{label}任务，请确认这是你准备的 Python 环境。\n\n{}\n\n本次设置不会安装依赖或自动启动计算。",
                path.display()
            );
            let confirmation = rfd::MessageDialog::new()
                .set_parent(&window)
                .set_title("使用所选执行环境")
                .set_description(description)
                .set_buttons(rfd::MessageButtons::OkCancelCustom(
                    "使用此环境".into(), "取消".into(),
                ))
                .show();
            Ok(if confirmation == rfd::MessageDialogResult::Custom("使用此环境".into()) {
                Some(path)
            } else {
                None
            })
        })
        .await
        .map_err(|_| error("FILE_DIALOG_FAILED", "无法选择执行环境。"))?;
        selected
    })
    .await
}

async fn select_python_environment<F>(
    state: &HostState,
    connection_id: &str,
    field: &'static str,
    selection: F,
) -> Result<Option<Value>, Value>
where
    F: std::future::Future<Output = Result<Option<PathBuf>, Value>>,
{
    let connection = bridge_connection(state, connection_id)?;
    let selected = complete_bridge_request(state, connection_id, selection.await)?;
    let result = async {
        let Some(path) = selected else {
            return Ok(None);
        };
        // Python 虚拟环境的可执行文件可能是符号链接，保留用户所选路径以维持环境身份。
        if !path.is_absolute()
            || !path.is_file()
            || !path
                .file_name()
                .is_some_and(|name| name.to_string_lossy().starts_with("python"))
        {
            return Err(error(
                "ENVIRONMENT_INVALID",
                "请选择已准备环境中存在的 Python 可执行文件。",
            ));
        }
        update_environment(state, &connection, field, Some(path), None)
            .await
            .map(Some)
    }
    .await;
    complete_bridge_request(state, connection_id, result)
}

#[tauri::command]
async fn use_bundled_worker(
    connection_id: String,
    state: State<'_, HostState>,
) -> Result<Value, Value> {
    use_bundled_environment(
        &state,
        &connection_id,
        "worker_python",
        "bundled_worker_available",
    )
    .await
}

#[tauri::command]
async fn use_bundled_media(
    engine: String,
    connection_id: String,
    state: State<'_, HostState>,
) -> Result<Value, Value> {
    let (field, _) = media_environment_field(&engine)?;
    let availability = if engine == "diffusers" {
        "bundled_media_worker_available"
    } else {
        "bundled_audio_worker_available"
    };
    use_bundled_environment(&state, &connection_id, field, availability).await
}

async fn use_bundled_environment(
    state: &HostState,
    connection_id: &str,
    field: &'static str,
    availability: &'static str,
) -> Result<Value, Value> {
    let connection = bridge_connection(state, connection_id)?;
    let result = update_environment(state, &connection, field, None, Some(availability)).await;
    complete_bridge_request(state, connection_id, result)
}

async fn update_environment(
    state: &HostState,
    connection: &Connection,
    field: &'static str,
    path: Option<PathBuf>,
    availability: Option<&'static str>,
) -> Result<Value, Value> {
    let _guard = reserve_host_change(
        state,
        &state.credential_busy,
        "HOST_CONFIGURATION_PENDING",
        "正在更新本地环境或连接，请完成后再设置执行环境。",
    )?;
    let current = native_connection_request(
        state,
        connection,
        ApiRequest {
            method: "GET".into(),
            path: "/api/v1/settings".into(),
            body: None,
            idempotency_key: None,
        },
    )
    .await?;
    if availability.is_some_and(|key| current.get(key).and_then(Value::as_bool) != Some(true)) {
        return Err(error(
            "ENVIRONMENT_INVALID",
            "内置执行环境不可用，请重新安装应用。",
        ));
    }
    let revision = current
        .get("revision")
        .and_then(Value::as_u64)
        .ok_or_else(|| error("ENVIRONMENT_INVALID", "无法读取当前环境版本。"))?;
    native_connection_request(
        state,
        connection,
        ApiRequest {
            method: "PATCH".into(),
            path: "/api/v1/settings".into(),
            body: Some(json!({
                field: path.map(|value| value.to_string_lossy().into_owned()),
                "expected_revision": revision,
            })),
            idempotency_key: None,
        },
    )
    .await
}

// 仅供宿主专用命令使用：复核身份，但始终向调用前捕获的连接发送请求。
// 不能退回 proxy()，否则排队或原生窗口返回后会借用新工作库身份。
async fn native_connection_request(
    state: &HostState,
    connection: &Connection,
    request: ApiRequest,
) -> Result<Value, Value> {
    bridge_connection(state, &connection.connection_id)?;
    let result = proxy_connection(state, request, false, connection.clone()).await;
    complete_bridge_request(state, &connection.connection_id, result)
}

fn launch_config(app: &tauri::AppHandle) -> Result<LaunchConfig, Box<dyn std::error::Error>> {
    let data_dir = if cfg!(debug_assertions) {
        std::env::var_os("AILAB_DATA_DIR")
            .map(PathBuf::from)
            .unwrap_or(app.path().app_data_dir()?)
    } else {
        app.path().app_data_dir()?
    };
    let bundled = app
        .path()
        .resource_dir()?
        .join("resources/control/ailab-control");
    if !cfg!(debug_assertions) {
        return Ok(LaunchConfig {
            executable: bundled,
            args: vec![
                "--bundled-worker".into(),
                app.path()
                    .resource_dir()?
                    .join("resources/mlx/ailab-mlx")
                    .to_string_lossy()
                    .into(),
                "--bundled-media-worker".into(),
                app.path()
                    .resource_dir()?
                    .join("resources/diffusers/ailab-diffusers")
                    .to_string_lossy()
                    .into(),
                "--bundled-audio-worker".into(),
                app.path()
                    .resource_dir()?
                    .join("resources/kokoro/ailab-kokoro")
                    .to_string_lossy()
                    .into(),
                "--worker-script".into(),
                app.path()
                    .resource_dir()?
                    .join("resources/workers/mlx_worker.py")
                    .to_string_lossy()
                    .into(),
                "--preflight-script".into(),
                app.path()
                    .resource_dir()?
                    .join("resources/adapters/mlx_text/preflight.py")
                    .to_string_lossy()
                    .into(),
            ],
            cwd: None,
            data_dir,
        });
    }
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../..")
        .canonicalize()?;
    let executable = std::env::var_os("AILAB_CONTROL_PYTHON")
        .map(PathBuf::from)
        .unwrap_or_else(|| root.join("services/control/.venv/bin/python"));
    let mut args = vec!["-m".into(), "ailab_control".into()];
    if let Some(value) = std::env::var_os("AILAB_WORKER_PYTHON") {
        args.extend(["--worker-python".into(), value.to_string_lossy().into()]);
    }
    args.extend([
        "--worker-script".into(),
        root.join("workers/mlx_worker.py").to_string_lossy().into(),
    ]);
    Ok(LaunchConfig {
        executable,
        args,
        cwd: Some(root.join("services/control")),
        data_dir,
    })
}

#[tauri::command]
fn complete_exit_preparation(
    request_id: u64,
    success: bool,
    state: State<'_, HostState>,
) -> Result<(), Value> {
    let accepted = state
        .exit_preparation
        .lock()
        .map_err(|_| error("HOST_STATE_ERROR", "无法读取退出保存状态。"))?
        .complete(request_id, success);
    if !accepted {
        return Err(error(
            "EXIT_PREPARATION_EXPIRED",
            "此退出保存回执已过期或与当前请求不匹配，请重试退出。",
        ));
    }
    Ok(())
}

fn request_exit(app: &tauri::AppHandle) {
    let state = app.state::<HostState>();
    if state.exiting.load(Ordering::SeqCst) || state.exit_dialog.swap(true, Ordering::SeqCst) {
        return;
    }
    let handle = app.clone();
    let Some(window) = app.get_webview_window("main") else {
        state.exit_dialog.store(false, Ordering::SeqCst);
        return;
    };
    let _ = window.show();
    tauri::async_runtime::spawn_blocking(move || {
        let result = rfd::MessageDialog::new().set_parent(&window).set_title("退出 GCSA AI Lab")
            .set_description("退出应用将停止本机正在执行的任务。任务记录会保留，重新打开后可继续查看。关闭窗口可以保留后台任务。")
            .set_buttons(rfd::MessageButtons::OkCancelCustom("退出并停止本机任务".into(), "继续使用".into())).show();
        let state = handle.state::<HostState>();
        if result == rfd::MessageDialogResult::Custom("退出并停止本机任务".into()) {
            const TIMEOUT: Duration = Duration::from_secs(30);
            let wait_started = Instant::now();
            let request = state
                .exit_preparation
                .lock()
                .ok()
                .and_then(|mut preparation| {
                    if state.switching.load(Ordering::SeqCst)
                        || state.credential_busy.load(Ordering::SeqCst)
                        || state.exiting.load(Ordering::SeqCst)
                    {
                        None
                    } else {
                        preparation.begin(TIMEOUT)
                    }
                });
            let Some((request_id, receiver)) = request else {
                rfd::MessageDialog::new()
                    .set_parent(&window)
                    .set_title("应用已保留")
                    .set_description("正在切换工作库或更新宿主连接，请完成后重试退出。")
                    .set_buttons(rfd::MessageButtons::Ok)
                    .show();
                state.exit_dialog.store(false, Ordering::SeqCst);
                return;
            };
            // 等待界面保存时不持有进程、启动或退出状态锁，普通 API 保存仍可进行。
            let received = if handle
                .emit(
                    "prepare-exit",
                    json!({"request_id":request_id,"cancelled":false}),
                )
                .is_ok()
            {
                receiver
                    .recv_timeout(TIMEOUT.saturating_sub(wait_started.elapsed()))
                    .ok()
            } else {
                None
            };
            let exit = state
                .exit_preparation
                .lock()
                .ok()
                .is_some_and(|mut preparation| {
                    let exit = preparation.finish(request_id, received) == Some(true);
                    if exit {
                        // 与清除 pending 同锁完成，不能在停服前插入切库或重配置。
                        state.exiting.store(true, Ordering::SeqCst);
                    }
                    exit
                });
            if exit {
                if let Ok(mut process) = state.process.lock() {
                    process.stop();
                }
                handle.exit(0);
            } else {
                let _ = handle.emit(
                    "prepare-exit",
                    json!({"request_id":request_id,"cancelled":true}),
                );
                rfd::MessageDialog::new()
                    .set_parent(&window)
                    .set_title("应用已保留")
                    .set_description(
                        "草稿或当前选择尚未保存，应用已保留，请处理界面中的提示后重试退出。",
                    )
                    .set_buttons(rfd::MessageButtons::Ok)
                    .show();
                state.exit_dialog.store(false, Ordering::SeqCst);
            }
        } else {
            state.exit_dialog.store(false, Ordering::SeqCst);
        }
    });
}

pub fn run() {
    let started = Instant::now();
    let app = tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![
            api_request,
            complete_exit_preparation,
            credentials::create_execution_target,
            credentials::connect_remote_target,
            credentials::forget_remote_target,
            api_media,
            host_status,
            record_first_frame,
            restart_control,
            pick_import_path,
            pick_export_directory,
            pick_worker_python,
            pick_media_python,
            use_bundled_worker,
            use_bundled_media,
            use_restored_library,
            configure_market_fixture
        ])
        .menu(|app| {
            use tauri::menu::{Menu, MenuItem, PredefinedMenuItem as Item, Submenu};
            let application = Submenu::with_items(
                app,
                "GCSA AI Lab",
                true,
                &[
                    &Item::about(app, Some("关于 GCSA AI Lab"), None)?,
                    &Item::separator(app)?,
                    &Item::hide(app, Some("隐藏 GCSA AI Lab"))?,
                    &Item::hide_others(app, Some("隐藏其他应用"))?,
                    &Item::separator(app)?,
                    &MenuItem::with_id(
                        app,
                        "quit-app",
                        "退出 GCSA AI Lab",
                        true,
                        Some("CmdOrCtrl+Q"),
                    )?,
                ],
            )?;
            let edit = Submenu::with_items(
                app,
                "编辑",
                true,
                &[
                    &Item::undo(app, Some("撤销"))?,
                    &Item::redo(app, Some("重做"))?,
                    &Item::separator(app)?,
                    &Item::cut(app, Some("剪切"))?,
                    &Item::copy(app, Some("复制"))?,
                    &Item::paste(app, Some("粘贴"))?,
                    &Item::select_all(app, Some("全选"))?,
                ],
            )?;
            let window = Submenu::with_items(
                app,
                "窗口",
                true,
                &[
                    &Item::minimize(app, Some("最小化"))?,
                    &Item::maximize(app, Some("缩放"))?,
                    &Item::close_window(app, Some("关闭窗口并保留后台任务"))?,
                ],
            )?;
            Menu::with_items(app, &[&application, &edit, &window])
        })
        .on_menu_event(|app, event| {
            if event.id().as_ref() == "quit-app" {
                request_exit(app);
            }
        })
        .setup(move |app| {
            let mut fallback = launch_config(app.handle())?;
            let selection_file = fallback.data_dir.join("selected-library.json");
            let settings_file = fallback.data_dir.join("host-settings.json");
            let startup = Mutex::new(startup::StartupMetrics::new(
                started,
                fallback.data_dir.join("startup-latest.json"),
            ));
            let settings = load_host_settings(&settings_file)?;
            configure_launch_fixture(&mut fallback, settings.market_fixture_origin.as_deref());
            let mut launch = fallback.clone();
            if let Ok(contents) = fs::read(&selection_file) {
                if let Ok(selection) = serde_json::from_slice::<LibrarySelection>(&contents) {
                    if let Ok(path) = restored_path(&selection.data_dir, &selection.restore_id) {
                        launch.data_dir = path;
                    }
                }
            }
            app.manage(HostState {
                process: Mutex::new(ControlProcess::default()),
                launch: Mutex::new(launch),
                fallback,
                selection_file,
                settings_file,
                client: reqwest::Client::builder()
                    .redirect(reqwest::redirect::Policy::none())
                    .no_proxy()
                    .timeout(Duration::from_secs(120))
                    .build()?,
                exiting: AtomicBool::new(false),
                exit_dialog: AtomicBool::new(false),
                exit_preparation: Mutex::new(exit_preparation::ExitPreparation::default()),
                switching: AtomicBool::new(false),
                credential_busy: AtomicBool::new(false),
                startup,
            });
            let handle = app.handle().clone();
            tauri::async_runtime::spawn(async move {
                let _ = restart_control(handle).await;
            });
            let handle = app.handle().clone();
            std::thread::spawn(move || {
                let mut previous = None;
                loop {
                    std::thread::sleep(Duration::from_millis(500));
                    let state = handle.state::<HostState>();
                    if state.exiting.load(Ordering::SeqCst) {
                        break;
                    }
                    let Ok(mut process) = state.process.lock() else {
                        break;
                    };
                    let status = process.status();
                    drop(process);
                    let Ok(launch) = state.launch.lock() else {
                        break;
                    };
                    let status = described_status(status, &launch);
                    drop(launch);
                    if previous.as_ref() != Some(&status) {
                        let _ = handle.emit("host-status", &status);
                        previous = Some(status);
                    }
                }
            });
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                api.prevent_close();
                let _ = window.hide();
            }
        })
        .build(tauri::generate_context!())
        .expect("GCSA AI Lab 桌面宿主启动失败");
    app.run(|app, event| match event {
        tauri::RunEvent::ExitRequested { api, .. } => {
            let state = app.state::<HostState>();
            if state.exiting.load(Ordering::SeqCst) {
                return;
            }
            api.prevent_exit();
            request_exit(app);
        }
        tauri::RunEvent::Exit => {
            if let Ok(mut process) = app.state::<HostState>().process.lock() {
                process.stop();
            }
        }
        #[cfg(target_os = "macos")]
        tauri::RunEvent::Reopen { .. } => {
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.show();
                let _ = window.set_focus();
            }
        }
        _ => {}
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn exit_preparation_ui_context只允许精确读取与保存路径() {
        for method in ["GET", "PATCH"] {
            let mut value = request("/api/v1/ui-context");
            value.method = method.into();
            value.body = (method == "PATCH").then(|| json!({}));
            assert!(validate_request(&value).is_ok());
            for path in [
                "/api/v1/ui-context/",
                "/api/v1/ui-context/extra",
                "/api/v1/ui-context?project_id=project-123",
                "/api/v1/ui-context?",
                "/api/v1/ui-context%2fsettings",
                "/api/v1/ui-context/../settings",
                "/api/v1/ui-context-evil",
            ] {
                value.path = path.into();
                assert!(
                    validate_request(&value).is_err(),
                    "意外允许：{method} {path}"
                );
            }
        }
        for method in ["POST", "PUT", "DELETE", "HEAD", "CONNECT"] {
            let mut value = request("/api/v1/ui-context");
            value.method = method.into();
            assert!(validate_request(&value).is_err(), "意外允许：{method}");
        }
        let mut value = request("/api/v1/ui-context");
        value.body = Some(json!({}));
        assert!(validate_request(&value).is_err());
    }

    #[test]
    fn exit_preparation保留环境设置与宿主入口保护() {
        assert!(validate_request(&request("/api/v1/settings")).is_ok());
        for path in [
            "/api/v1/settings",
            "/api/v1/settings/worker_python",
            "/api/v1/host/reconfiguration",
        ] {
            for method in ["POST", "PUT", "PATCH", "DELETE"] {
                let mut value = request(path);
                value.method = method.into();
                value.body = Some(json!({"worker_python":"/tmp/arbitrary"}));
                assert!(
                    validate_request(&value).is_err(),
                    "意外允许：{method} {path}"
                );
            }
        }
    }

    #[test]
    fn exit_preparation阻止宿主变更但不设置普通写入门禁() {
        let dir = tempfile::tempdir().unwrap();
        let launch = LaunchConfig {
            executable: dir.path().join("never-run"),
            args: vec![],
            cwd: None,
            data_dir: dir.path().into(),
        };
        let state = HostState {
            process: Mutex::new(ControlProcess::default()),
            launch: Mutex::new(launch.clone()),
            fallback: launch,
            selection_file: dir.path().join("selection.json"),
            settings_file: dir.path().join("settings.json"),
            client: reqwest::Client::new(),
            exiting: AtomicBool::new(false),
            exit_dialog: AtomicBool::new(true),
            exit_preparation: Mutex::new(exit_preparation::ExitPreparation::default()),
            switching: AtomicBool::new(false),
            credential_busy: AtomicBool::new(false),
            startup: Mutex::new(startup::StartupMetrics::new(
                Instant::now(),
                dir.path().join("startup.json"),
            )),
        };
        let (id, _receiver) = state
            .exit_preparation
            .lock()
            .unwrap()
            .begin(Duration::from_secs(30))
            .unwrap();
        for flag in [&state.switching, &state.credential_busy] {
            let denied = reserve_host_change(&state, flag, "BUSY", "进行中");
            assert_eq!(
                denied.err().unwrap()["error"]["code"],
                "EXIT_PREPARATION_PENDING"
            );
            assert!(!flag.load(Ordering::SeqCst));
        }
        assert!(!state.exiting.load(Ordering::SeqCst));
        for path in ["/api/v1/tasks/task-123/draft", "/api/v1/ui-context"] {
            let mut value = request(path);
            value.method = "PATCH".into();
            value.body = Some(json!({}));
            assert!(validate_request(&value).is_ok());
        }
        assert_eq!(
            state.exit_preparation.lock().unwrap().finish(id, None),
            Some(false)
        );
        {
            let _guard = reserve_host_change(&state, &state.switching, "BUSY", "进行中").unwrap();
            assert!(state.switching.load(Ordering::SeqCst));
        }
        assert!(!state.switching.load(Ordering::SeqCst));
        state.exiting.store(true, Ordering::SeqCst);
        assert!(reserve_host_change(&state, &state.switching, "BUSY", "进行中").is_err());
        assert!(!state.switching.load(Ordering::SeqCst));
    }

    #[test]
    fn 远端凭据只能经原生命令读写() {
        let target = format!(
            "/api/v1/execution-targets/execution-target-{}",
            "a".repeat(32)
        );
        for path in ["/api/v1/execution-targets".to_owned(), target.clone()] {
            assert!(validate_request(&request(&path)).is_ok());
        }
        let mut check = request(&format!("{target}/check"));
        check.method = "POST".into();
        check.body = Some(json!({}));
        assert!(validate_request(&check).is_ok());
        check.body = Some(json!({"credential_token": "x".repeat(40)}));
        assert!(validate_request(&check).is_err());
        for path in [
            "/api/v1/execution-targets".to_owned(),
            format!("{target}/credentials"),
            "/api/v1/host/execution-targets".into(),
        ] {
            for method in ["POST", "PATCH", "DELETE"] {
                let mut value = request(&path);
                value.method = method.into();
                value.body = Some(
                    json!({"credential_token": "x".repeat(40), "credential_ref": "remote-credential-".to_owned() + &"b".repeat(32)}),
                );
                assert!(validate_request(&value).is_err());
            }
        }
        assert!(
            validate_request(&request("/api/v1/remote-transfers?project_id=project-test")).is_ok()
        );
        for path in [
            "/api/v1/remote-transfers",
            "/api/v1/remote-transfers/prepare",
        ] {
            let mut value = request(path);
            value.method = "POST".into();
            value.body = Some(json!({"project_id": "project-test"}));
            assert!(validate_request(&value).is_ok());
        }
        for path in [
            "/api/v1/remote-transfers/credentials",
            "/api/v1/remote-transfers/prepare",
        ] {
            assert!(validate_request(&request(path)).is_err());
        }
    }

    #[test]
    fn fixture_configuration_is_explicit_local_and_preserves_library_arguments() {
        assert!(validate_fixture_origin(None).is_ok());
        for origin in ["http://127.0.0.1:1", "http://127.0.0.1:65535"] {
            assert!(validate_fixture_origin(Some(origin)).is_ok());
        }
        for origin in [
            "",
            "http://127.0.0.1:0",
            "http://127.0.0.1:01",
            "http://127.0.0.1:65536",
            "http://127.0.0.1:+1",
            "http://127.0.0.1:80/",
            "http://127.0.0.1:80?x=1",
            "http://127.0.0.1:80#x",
            "http://localhost:80",
            "http://user@127.0.0.1:80",
            "https://127.0.0.1:80",
            "http://127.0.0.1:80\n",
            "http://192.168.1.2:80",
        ] {
            assert!(
                validate_fixture_origin(Some(origin)).is_err(),
                "意外允许：{origin}"
            );
        }
        let mut launch = LaunchConfig {
            executable: "/app/control".into(),
            args: vec!["--bundled-worker".into(), "/app/worker".into()],
            cwd: None,
            data_dir: "/restored/library".into(),
        };
        configure_launch_fixture(&mut launch, Some("http://127.0.0.1:2345"));
        configure_launch_fixture(&mut launch, Some("http://127.0.0.1:3456"));
        assert_eq!(
            fixture_origin(&launch).as_deref(),
            Some("http://127.0.0.1:3456")
        );
        assert_eq!(launch.args.len(), 4);
        assert_eq!(launch.data_dir, PathBuf::from("/restored/library"));
        let status = described_status(HostStatus::stopped("已停止"), &launch);
        assert_eq!(status["market_fixture_origin"], "http://127.0.0.1:3456");
        configure_launch_fixture(&mut launch, None);
        assert_eq!(launch.args, vec!["--bundled-worker", "/app/worker"]);
        assert!(
            described_status(HostStatus::stopped("已停止"), &launch)["market_fixture_origin"]
                .is_null()
        );
        for method in ["GET", "POST", "DELETE"] {
            let mut value = request("/api/v1/host/reconfiguration");
            value.method = method.into();
            assert!(validate_request(&value).is_err());
        }
    }

    #[test]
    fn saved_fixture_settings_reject_external_unknown_and_linked_inputs() {
        let directory = tempfile::tempdir().unwrap();
        let path = directory.path().join("host-settings.json");
        assert!(load_host_settings(&path)
            .unwrap()
            .market_fixture_origin
            .is_none());
        fs::write(
            &path,
            br#"{"market_fixture_origin":"http://127.0.0.1:8765"}"#,
        )
        .unwrap();
        assert_eq!(
            load_host_settings(&path)
                .unwrap()
                .market_fixture_origin
                .as_deref(),
            Some("http://127.0.0.1:8765")
        );
        for contents in [
            br#"{"market_fixture_origin":"http://example.com:8765"}"#.as_slice(),
            br#"{"market_fixture_origin":null,"worker_script":"/tmp/other.py"}"#.as_slice(),
            b"invalid",
        ] {
            fs::write(&path, contents).unwrap();
            assert!(load_host_settings(&path).is_err());
        }
        fs::remove_file(&path).unwrap();
        let external = directory.path().join("external.json");
        fs::write(&external, b"{}").unwrap();
        std::os::unix::fs::symlink(&external, &path).unwrap();
        assert!(load_host_settings(&path).is_err());
    }

    async fn media_fixture(response: &[u8], maximum: usize) -> Result<Value, Value> {
        use std::io::{Read, Write};
        let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let address = listener.local_addr().unwrap();
        let response = response.to_vec();
        let server = std::thread::spawn(move || {
            let (mut stream, _) = listener.accept().unwrap();
            let mut request = [0_u8; 1024];
            assert!(stream.read(&mut request).unwrap() > 0);
            stream.write_all(&response).unwrap();
        });
        let response = reqwest::get(format!("http://{address}/content"))
            .await
            .unwrap();
        let result = media_response(response, maximum).await;
        server.join().unwrap();
        result
    }

    #[test]
    fn media_path_only_accepts_registered_artifact_identifiers() {
        assert_eq!(
            media_path(&format!("artifact-{}", "a".repeat(32))).unwrap(),
            format!("/api/v1/artifacts/artifact-{}/content", "a".repeat(32))
        );
        for value in [
            "artifact-a",
            "../outside",
            "https://example.com",
            "artifact-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa?path=/outside",
            "artifact-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        ] {
            assert_eq!(
                media_path(value).unwrap_err()["error"]["code"],
                "MEDIA_REQUEST_DENIED"
            );
        }
    }

    #[test]
    fn media_environment_selection_is_limited_to_known_runtime_fields() {
        assert_eq!(
            media_environment_field("diffusers").unwrap().0,
            "media_python"
        );
        assert_eq!(media_environment_field("kokoro").unwrap().0, "audio_python");
        let field = media_environment_field("diffusers").unwrap().0;
        assert_eq!(
            json!({field:"/selected/python", "expected_revision":1})["media_python"],
            "/selected/python"
        );
        for value in [
            "worker_python",
            "media_worker_script",
            "/bin/sh",
            "python -c print(1)",
            "unknown",
        ] {
            assert_eq!(
                media_environment_field(value).unwrap_err()["error"]["code"],
                "ENVIRONMENT_INVALID"
            );
        }
    }

    #[test]
    fn media_response_preserves_bytes_and_rejects_unsafe_or_oversized_content() {
        tauri::async_runtime::block_on(async {
            for mime in ["image/png", "video/mp4", "audio/wav"] {
                let mut response =
                    format!("HTTP/1.1 200 OK\r\nContent-Type: {mime}\r\nContent-Length: 3\r\n\r\n")
                        .into_bytes();
                response.extend_from_slice(&[0, 1, 255]);
                let result = media_fixture(&response, 8).await.unwrap();
                assert_eq!(result["media_type"], mime);
                assert_eq!(result["base64"], "AAH/");
            }
            for (response, code) in [
                (b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Length: 4\r\n\r\noops".as_slice(), "MEDIA_RESPONSE_INVALID"),
                (b"HTTP/1.1 200 OK\r\nContent-Type: image/png\r\nContent-Length: 100\r\n\r\n".as_slice(), "MEDIA_RESPONSE_TOO_LARGE"),
                (b"HTTP/1.1 200 OK\r\nContent-Type: video/mp4\r\nTransfer-Encoding: chunked\r\n\r\n5\r\n12345\r\n5\r\n67890\r\n0\r\n\r\n".as_slice(), "MEDIA_RESPONSE_TOO_LARGE"),
                (b"HTTP/1.1 200 OK\r\nContent-Type: audio/wav\r\nContent-Length: 0\r\n\r\n".as_slice(), "MEDIA_RESPONSE_INVALID"),
            ] {
                assert_eq!(media_fixture(response, 8).await.unwrap_err()["error"]["code"], code);
            }
            let body = br#"{"error":{"code":"ARTIFACT_CORRUPT","message":"fixture"}}"#;
            let mut response = format!("HTTP/1.1 409 Conflict\r\nContent-Type: application/json\r\nContent-Length: {}\r\n\r\n", body.len()).into_bytes();
            response.extend_from_slice(body);
            assert_eq!(
                media_fixture(&response, 8).await.unwrap_err()["error"]["code"],
                "ARTIFACT_CORRUPT"
            );
        });
    }

    fn request(path: &str) -> ApiRequest {
        ApiRequest {
            method: "GET".into(),
            path: path.into(),
            body: None,
            idempotency_key: None,
        }
    }
    #[test]
    fn training_contracts_proxy_only_accepts_static_get() {
        assert!(validate_request(&request("/api/v1/training-contracts")).is_ok());
        for (method, path) in [
            ("POST", "/api/v1/training-contracts"),
            ("PATCH", "/api/v1/training-contracts"),
            ("PUT", "/api/v1/training-contracts"),
            ("DELETE", "/api/v1/training-contracts"),
            ("GET", "/api/v1/training-contracts/execute"),
            ("POST", "/api/v1/training-contracts/execute"),
        ] {
            let mut value = request(path);
            value.method = method.into();
            assert_eq!(
                validate_request(&value).unwrap_err()["error"]["code"],
                "HOST_REQUEST_DENIED",
                "意外允许：{method} {path}"
            );
        }
        let mut value = request("/api/v1/training-contracts");
        value.body = Some(json!({}));
        assert_eq!(
            validate_request(&value).unwrap_err()["error"]["code"],
            "HOST_REQUEST_DENIED"
        );
    }
    #[test]
    fn market_proxy_only_accepts_declared_source_actions() {
        for (method, path) in [
            ("GET", "/api/v1/market/sources"),
            (
                "GET",
                "/api/v1/market/catalog?project_id=project-1&provider_id=fixture",
            ),
            (
                "GET",
                "/api/v1/market/local-versions?project_id=project-1&provider_id=fixture",
            ),
            ("GET", "/api/v1/market/versions/version-1/activity"),
            ("POST", "/api/v1/market/access-requests"),
            ("POST", "/api/v1/market/access-requests/request-1/refresh"),
            ("POST", "/api/v1/market/downloads"),
            ("GET", "/api/v1/market/downloads/download-1"),
            ("POST", "/api/v1/market/downloads/download-1/cancel"),
            ("POST", "/api/v1/market/downloads/download-1/resume"),
            ("POST", "/api/v1/market/downloads/download-1/datasets"),
            ("POST", "/api/v1/market/contexts/context-1/use"),
            ("POST", "/api/v1/tasks/task-1/market-contexts"),
            ("POST", "/api/v1/works/work-1/revisions"),
        ] {
            let mut value = request(path);
            value.method = method.into();
            assert!(validate_request(&value).is_ok(), "{method} {path}");
        }
        for (method, path) in [
            ("POST", "/api/v1/market/sources"),
            ("POST", "/api/v1/market/local-versions"),
            ("GET", "/api/v1/market/local-versions/version-1"),
            ("POST", "/api/v1/market/local-versions/version-1"),
            ("PATCH", "/api/v1/market/sources/fixture"),
            ("POST", "/api/v1/market/providers"),
            ("POST", "/api/v1/market/access-requests/request-1/approve"),
            ("POST", "/api/v1/market/access-requests/request-1/revoke"),
            ("GET", "/api/v1/market/files/arbitrary"),
            ("POST", "/api/v1/market/downloads/download-1/execute"),
            ("DELETE", "/api/v1/market/downloads/download-1"),
            ("GET", "/api/v1/market/contexts/context-1/use"),
        ] {
            let mut value = request(path);
            value.method = method.into();
            assert_eq!(
                validate_request(&value).unwrap_err()["error"]["code"],
                "HOST_REQUEST_DENIED"
            );
        }
    }
    #[test]
    fn model_download_proxy_is_limited_to_catalog_and_registered_actions() {
        let id = format!("model-download-{}", "a".repeat(32));
        for (method, path) in [
            ("GET", "/api/v1/model-catalog".into()),
            ("GET", "/api/v1/model-downloads?project_id=project-1".into()),
            ("POST", "/api/v1/model-downloads".into()),
            ("GET", format!("/api/v1/model-downloads/{id}")),
            ("POST", format!("/api/v1/model-downloads/{id}/resume")),
            ("POST", format!("/api/v1/model-downloads/{id}/cancel")),
            ("POST", format!("/api/v1/model-downloads/{id}/models")),
        ] {
            let mut value = request(&path);
            value.method = method.into();
            assert!(
                validate_request(&value).is_ok(),
                "意外拒绝：{method} {path}"
            );
        }
        for (method, path) in [
            ("POST", "/api/v1/model-catalog".into()),
            ("GET", "/api/v1/model-catalog/custom-url".into()),
            ("GET", "/api/v1/model-downloads/model-download-123".into()),
            (
                "GET",
                format!("/api/v1/model-downloads/model-download-{}", "A".repeat(32)),
            ),
            ("DELETE", format!("/api/v1/model-downloads/{id}")),
            ("GET", format!("/api/v1/model-downloads/{id}/resume")),
            ("POST", format!("/api/v1/model-downloads/{id}/execute")),
            ("POST", format!("/api/v1/model-downloads/{id}/files")),
        ] {
            let mut value = request(&path);
            value.method = method.into();
            assert!(
                validate_request(&value).is_err(),
                "意外允许：{method} {path}"
            );
        }
    }
    #[test]
    fn diagnostics_proxy_only_accepts_preview_cancel_and_export() {
        let id = format!("diagnostic-preview-{}", "b".repeat(32));
        for (method, path) in [
            ("POST", "/api/v1/diagnostics/previews".into()),
            ("GET", format!("/api/v1/diagnostics/previews/{id}")),
            ("POST", format!("/api/v1/diagnostics/previews/{id}/cancel")),
            ("POST", "/api/v1/diagnostics/exports".into()),
        ] {
            let mut value = request(&path);
            value.method = method.into();
            assert!(
                validate_request(&value).is_ok(),
                "意外拒绝：{method} {path}"
            );
        }
        for (method, path) in [
            ("GET", "/api/v1/diagnostics".into()),
            ("GET", "/api/v1/diagnostics/exports".into()),
            (
                "GET",
                "/api/v1/diagnostics/previews/diagnostic-preview-123".into(),
            ),
            (
                "GET",
                format!(
                    "/api/v1/diagnostics/previews/diagnostic-preview-{}",
                    "B".repeat(32)
                ),
            ),
            ("DELETE", format!("/api/v1/diagnostics/previews/{id}")),
            ("POST", format!("/api/v1/diagnostics/previews/{id}/upload")),
            ("GET", "/api/v1/diagnostics/files/system".into()),
        ] {
            let mut value = request(&path);
            value.method = method.into();
            assert!(
                validate_request(&value).is_err(),
                "意外允许：{method} {path}"
            );
        }
    }
    #[test]
    fn proxy_accepts_business_path_and_query() {
        assert!(
            validate_request(&request("/api/v1/tasks?project_id=project_123&limit=50")).is_ok()
        );
        assert!(validate_request(&request("/api/v1/attempts/ab-12/events?after=1")).is_ok());
        for path in [
            "/api/v1/adapters?project_id=project_123",
            "/api/v1/collections/c_123",
            "/api/v1/checkpoints?attempt_id=attempt_123",
            "/api/v1/cleanups",
            "/api/v1/materials?project_id=project_123",
            "/api/v1/evaluation-plans/ep_123",
            "/api/v1/candidates/c_123",
            "/api/v1/settings",
        ] {
            assert!(validate_request(&request(path)).is_ok(), "意外拒绝：{path}");
        }
        for path in [
            "/api/v1/attempts/ab-12/adapters",
            "/api/v1/attempts/ab-12/collections",
            "/api/v1/exports",
            "/api/v1/evaluation-plans",
            "/api/v1/candidates/c_123/register",
            "/api/v1/backups",
            "/api/v1/restore-plans",
            "/api/v1/restores",
            "/api/v1/conversions",
            "/api/v1/attempts/ab-12/converted-models",
            "/api/v1/checkpoints/checkpoint-123/restore-task",
            "/api/v1/cleanup-plans",
            "/api/v1/cleanups",
            "/api/v1/cleanups/cleanup-123/restore",
            "/api/v1/materials/import-plans",
            "/api/v1/materials/imports",
        ] {
            let mut value = request(path);
            value.method = "POST".into();
            value.body = Some(json!({}));
            assert!(validate_request(&value).is_ok(), "意外拒绝：{path}");
        }
    }
    #[test]
    fn proxy_rejects_urls_traversal_and_grant_forgery() {
        for path in [
            "/api/v1/restores/restore_123/activation",
            "https://example.com/api/v1/projects",
            "//example.com/api/v1/projects",
            "/api/v1/../secret",
            "/api/v1/%2e%2e/secret",
            "/api/v1/projects%2F..%2Fsecret",
            "/api/v1/import-grants",
            "/api/v1/export-grants",
            "/api/v1/projects#secret",
            "/api/v1//projects",
            "/api/v1/projects\\secret",
            "/api/v1/projects\r\nHost: evil",
        ] {
            assert!(
                validate_request(&request(path)).is_err(),
                "意外允许：{path}"
            );
        }
    }

    #[test]
    fn ai_and_workflow_routes_keep_host_settings_and_grants_closed() {
        for path in [
            "/api/v1/ai/requests",
            "/api/v1/ai/requests/request-123",
            "/api/v1/ai/proposals/proposal-123",
            "/api/v1/workflow-runs/run-123",
        ] {
            assert!(validate_request(&request(path)).is_ok(), "意外拒绝：{path}");
        }
        for path in [
            "/api/v1/ai/requests",
            "/api/v1/ai/requests/request-123/proposals",
            "/api/v1/ai/proposals/proposal-123/apply",
            "/api/v1/ai/proposals/proposal-123/undo",
            "/api/v1/workflow-runs",
        ] {
            let mut value = request(path);
            value.method = "POST".into();
            value.body = Some(json!({}));
            assert!(validate_request(&value).is_ok(), "意外拒绝：{path}");
        }
        for path in [
            "/api/v1/ai/settings",
            "/api/v1/ai/import-grants",
            "/api/v1/ai/requests/request-123/settings",
            "/api/v1/ai/proposals/proposal-123/execute",
            "/api/v1/workflows",
            "/api/v1/settings",
            "/api/v1/import-grants",
        ] {
            let mut value = request(path);
            value.method = "POST".into();
            value.body = Some(json!({}));
            assert!(validate_request(&value).is_err(), "意外放行：{path}");
        }
    }

    #[test]
    fn restored_library_requires_matching_receipt_and_regular_paths() {
        let dir = tempfile::tempdir().unwrap();
        let root = dir.path().canonicalize().unwrap();
        fs::write(root.join("control.sqlite3"), b"fixture").unwrap();
        fs::write(
            root.join("restoration.json"),
            br#"{"restore_id":"restore-123"}"#,
        )
        .unwrap();
        assert!(restored_path(&root, "restore-123").is_ok());
        assert!(restored_path(&root, "restore-other").is_err());
        let link = root.join("linked");
        #[cfg(unix)]
        std::os::unix::fs::symlink(&root, &link).unwrap();
        assert!(restored_path(&link, "restore-123").is_err());
        fs::remove_file(root.join("control.sqlite3")).unwrap();
        assert!(restored_path(&root, "restore-123").is_err());
    }
    #[test]
    fn proxy_rejects_unsafe_headers_methods_and_large_body() {
        let mut value = request("/api/v1/tasks");
        value.method = "CONNECT".into();
        assert!(validate_request(&value).is_err());
        value.method = "POST".into();
        value.idempotency_key = Some("x\r\nAuthorization: other".into());
        assert!(validate_request(&value).is_err());
        value.idempotency_key = None;
        value.body = Some(json!("x".repeat(1024 * 1024)));
        assert!(validate_request(&value).is_err());
        let mut setting = request("/api/v1/settings");
        setting.method = "PATCH".into();
        assert!(validate_request(&setting).is_err());
        for path in [
            "/api/v1/settings",
            "/api/v1/settings/worker_python",
            "/api/v1/import-grants",
            "/api/v1/export-grants",
            "/api/v1/adapters-evil",
            "/api/v1/shell",
        ] {
            for method in ["POST", "PATCH", "PUT", "DELETE"] {
                let mut value = request(path);
                value.method = method.into();
                value.body = Some(json!({"worker_python":"/tmp/arbitrary"}));
                assert!(
                    validate_request(&value).is_err(),
                    "意外允许：{method} {path}"
                );
            }
        }
    }
}
