//! 用临时 HTTP 控制服务检查连接换代；不接触真实工作库、App 或钥匙串。

use super::*;

const ARTIFACT_ID: &str = "artifact-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";

// 两个服务接受相同的资源编号，故不能依赖 project/task ID 区分工作库。
// 只记录 method/path/body；认证只比较，不写进回执。
const CONTROL_FIXTURE: &str = r#"
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

root = Path(sys.argv[sys.argv.index('--data-dir') + 1])
token = 't' * 48
host_token = 'h' * 48

class Handler(BaseHTTPRequestHandler):
    def handle_request(self):
        length = int(self.headers.get('Content-Length', '0'))
        raw = self.rfile.read(length)
        body = json.loads(raw) if raw else None
        if self.path == '/health':
            result = {'status': 'ok'}
        else:
            with (root / 'requests.jsonl').open('a', encoding='utf-8') as output:
                output.write(json.dumps({'method': self.command, 'path': self.path, 'body': body}) + '\n')
            authorized = self.headers.get('Authorization') == 'Bearer ' + token
            host_authorized = self.headers.get('X-AiLab-Host-Token') == host_token
            if not authorized or (self.path.startswith('/api/v1/host/') and not host_authorized):
                self.send_json({'error': {'code': 'FIXTURE_AUTH_FAILED'}}, 403)
                return
            if self.path.endswith('/content'):
                content = bytes([0, 1, 255])
                self.send_response(200)
                self.send_header('Content-Type', 'image/png')
                self.send_header('Content-Length', str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                return
            result = {'library': root.name, 'method': self.command, 'path': self.path,
                      'body': body, 'host_authorized': host_authorized}
        self.send_json(result, 200)

    def send_json(self, value, status):
        content = json.dumps(value).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    do_GET = do_POST = do_PATCH = do_DELETE = handle_request

    def log_message(self, *args):
        pass

server = HTTPServer(('127.0.0.1', 0), Handler)
print(json.dumps({'port': server.server_port, 'pid': os.getpid(),
                  'token': token, 'host_token': host_token}), flush=True)
server.serve_forever()
"#;

struct ScopeFixture {
    // 先释放服务，再删除临时目录；断言失败时也由 ControlProcess 回收子进程。
    state: HostState,
    directory: tempfile::TempDir,
}

impl ScopeFixture {
    fn new() -> Self {
        let directory = tempfile::tempdir().unwrap();
        let script = directory.path().join("control-fixture.py");
        fs::write(&script, CONTROL_FIXTURE).unwrap();
        let launch = LaunchConfig {
            executable: "/usr/bin/python3".into(),
            args: vec![script.to_string_lossy().into_owned()],
            cwd: None,
            data_dir: directory.path().join("a"),
        };
        let mut process = ControlProcess::default();
        process.start(&launch).unwrap();
        let state = HostState {
            process: Mutex::new(process),
            launch: Mutex::new(launch.clone()),
            fallback: launch,
            selection_file: directory.path().join("selection.json"),
            settings_file: directory.path().join("settings.json"),
            client: reqwest::Client::builder()
                .no_proxy()
                .redirect(reqwest::redirect::Policy::none())
                .timeout(Duration::from_secs(3))
                .build()
                .unwrap(),
            exiting: AtomicBool::new(false),
            exit_dialog: AtomicBool::new(false),
            exit_preparation: Mutex::new(exit_preparation::ExitPreparation::default()),
            switching: AtomicBool::new(false),
            credential_busy: AtomicBool::new(false),
            startup: Mutex::new(startup::StartupMetrics::new(
                Instant::now(),
                directory.path().join("startup.json"),
            )),
        };
        Self { state, directory }
    }

    fn connection_id(&self) -> String {
        self.state
            .process
            .lock()
            .unwrap()
            .connection()
            .unwrap()
            .connection_id
    }

    fn switch_to(&self, name: &str) -> String {
        let current = self.state.launch.lock().unwrap().clone();
        let mut next = current.clone();
        next.data_dir = self.directory.path().join(name);
        self.state.switching.store(true, Ordering::SeqCst);
        let status = self
            .state
            .process
            .lock()
            .unwrap()
            .switch_library(&current, &next, &self.state.selection_file, name.as_bytes())
            .unwrap();
        *self.state.launch.lock().unwrap() = next;
        self.state.switching.store(false, Ordering::SeqCst);
        let id = status.connection_id.unwrap();
        assert_eq!(id, self.connection_id());
        id
    }

    fn requests(&self, name: &str) -> Vec<Value> {
        let contents =
            match fs::read_to_string(self.directory.path().join(name).join("requests.jsonl")) {
                Ok(contents) => contents,
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => return vec![],
                Err(error) => panic!("读取夹具请求记录失败：{error}"),
            };
        contents
            .lines()
            .map(|line| serde_json::from_str(line).unwrap())
            .collect()
    }
}

fn request(method: &str, path: &str, body: Option<Value>) -> ApiRequest {
    ApiRequest {
        method: method.into(),
        path: path.into(),
        body,
        idempotency_key: None,
    }
}

fn ui_request() -> ApiRequest {
    request(
        "PATCH",
        "/api/v1/ui-context",
        Some(json!({
            "project_id": "project-shared-between-a-and-b",
            "context": {
                "page": "home", "kind": "image", "module_tab": "train", "data_tab": "local",
                "task_id": "task-shared-between-a-and-b", "workflow_id": null,
                "recent_tasks": {"image:train": "task-shared-between-a-and-b"}
            }
        })),
    )
}

fn scoped(request: ApiRequest, connection_id: &str) -> BridgeApiRequest {
    BridgeApiRequest {
        request,
        connection_id: connection_id.into(),
    }
}

fn assert_code(result: Result<Value, Value>, code: &str) {
    assert_eq!(result.unwrap_err()["error"]["code"], code);
}

#[test]
fn bridge_requires_the_frontend_connection_id() {
    let mut value = json!({"method": "GET", "path": "/api/v1/projects"});
    assert!(serde_json::from_value::<BridgeApiRequest>(value.clone()).is_err());
    value["connection_id"] = Value::Null;
    assert!(serde_json::from_value::<BridgeApiRequest>(value.clone()).is_err());
    value["connection_id"] = json!("42");
    let request: BridgeApiRequest = serde_json::from_value(value).unwrap();
    assert_eq!(request.connection_id, "42");
    assert_eq!(request.request.path, "/api/v1/projects");
}

#[test]
fn request_waiting_for_the_process_lock_cannot_adopt_the_new_connection() {
    let fixture = ScopeFixture::new();
    let old_id = fixture.connection_id();
    let current = fixture.state.launch.lock().unwrap().clone();
    let mut next = current.clone();
    next.data_dir = fixture.directory.path().join("b");
    let mut process = fixture.state.process.lock().unwrap();
    let (started, ready) = std::sync::mpsc::channel();
    std::thread::scope(|scope| {
        let waiting = scope.spawn(|| {
            started.send(()).unwrap();
            tauri::async_runtime::block_on(bridge_request(
                &fixture.state,
                scoped(ui_request(), &old_id),
            ))
        });
        ready.recv().unwrap();
        fixture.state.switching.store(true, Ordering::SeqCst);
        process
            .switch_library(&current, &next, &fixture.state.selection_file, b"b")
            .unwrap();
        // 持锁到切换旗标复位，强制覆盖原先“锁前已检查”的失效窗口。
        fixture.state.switching.store(false, Ordering::SeqCst);
        drop(process);
        assert_code(waiting.join().unwrap(), "CONTROL_CONNECTION_CHANGED");
    });
    assert!(fixture.requests("b").is_empty());
}

#[test]
fn restart_and_library_switch_reservations_are_mutually_exclusive() {
    let fixture = ScopeFixture::new();
    let state = &fixture.state;
    for (held, contender, expected) in [
        (
            &state.switching,
            &state.credential_busy,
            "LIBRARY_SWITCH_PENDING",
        ),
        (
            &state.credential_busy,
            &state.switching,
            "CREDENTIAL_OPERATION_PENDING",
        ),
    ] {
        let guard = reserve_host_change(state, held, "BUSY", "进行中").unwrap();
        let denied = reserve_host_change(state, contender, "BUSY", "进行中");
        assert_eq!(denied.err().unwrap()["error"]["code"], expected);
        assert!(held.load(Ordering::SeqCst));
        assert!(!contender.load(Ordering::SeqCst));
        drop(guard);
    }
    let barrier = std::sync::Barrier::new(2);
    std::thread::scope(|scope| {
        let attempt = |busy| {
            barrier.wait();
            let result = reserve_host_change(state, busy, "BUSY", "进行中");
            // 成功者保留门禁，直到另一方也完成申请。
            barrier.wait();
            result.is_ok()
        };
        let switching = scope.spawn(move || attempt(&state.switching));
        let restarting = scope.spawn(move || attempt(&state.credential_busy));
        assert_eq!(
            switching.join().unwrap() as u8 + restarting.join().unwrap() as u8,
            1
        );
    });
    assert!(!state.switching.load(Ordering::SeqCst));
    assert!(!state.credential_busy.load(Ordering::SeqCst));
}

#[test]
fn stale_patch_get_and_media_never_reach_the_new_library() {
    tauri::async_runtime::block_on(async {
        let fixture = ScopeFixture::new();
        let a_id = fixture.connection_id();
        // 旧请求延迟到 B 已连接且 switching 复位后才进入桥接函数。
        let b_id = fixture.switch_to("b");
        assert_ne!(a_id, b_id);
        let old_patch = bridge_request(&fixture.state, scoped(ui_request(), &a_id)).await;
        assert!(
            old_patch.is_err(),
            "旧 PATCH 被新库接收：result={old_patch:?}，B HTTP={:?}",
            fixture.requests("b")
        );
        assert_code(old_patch, "CONTROL_CONNECTION_CHANGED");
        assert_code(
            bridge_request(
                &fixture.state,
                scoped(request("GET", "/api/v1/projects", None), &a_id),
            )
            .await,
            "CONTROL_CONNECTION_CHANGED",
        );
        assert_code(
            bridge_media(&fixture.state, ARTIFACT_ID.into(), a_id.clone()).await,
            "CONTROL_CONNECTION_CHANGED",
        );
        assert!(fixture.requests("b").is_empty(), "旧连接请求不得发往 B");

        let saved = bridge_request(&fixture.state, scoped(ui_request(), &b_id))
            .await
            .unwrap();
        assert_eq!(saved["library"], "b");
        assert_eq!(saved["body"], ui_request().body.unwrap());
        let loaded = bridge_request(
            &fixture.state,
            scoped(request("GET", "/api/v1/projects", None), &b_id),
        )
        .await
        .unwrap();
        assert_eq!(loaded["library"], "b");
        let media = bridge_media(&fixture.state, ARTIFACT_ID.into(), b_id)
            .await
            .unwrap();
        assert_eq!(media, json!({"media_type": "image/png", "base64": "AAH/"}));
        let received = fixture.requests("b");
        assert_eq!(received.len(), 3);
        assert_eq!(received[0]["method"], "PATCH");
        assert_eq!(received[0]["path"], "/api/v1/ui-context");
        assert_eq!(received[0]["body"], ui_request().body.unwrap());
        assert_eq!(received[1]["path"], "/api/v1/projects");
        assert_eq!(received[2]["path"], media_path(ARTIFACT_ID).unwrap());
    });
}

#[test]
fn completion_discards_both_success_and_failure_from_an_old_connection() {
    let fixture = ScopeFixture::new();
    let a_id = fixture.connection_id();
    let old_success = Ok(json!({"library": "a", "value": "旧成功结果"}));
    let old_failure = Err(error("OLD_LIBRARY_ERROR", "旧库失败结果"));
    let b_id = fixture.switch_to("b");
    for result in [old_success, old_failure] {
        assert_code(
            complete_bridge_request(&fixture.state, &a_id, result),
            "CONTROL_CONNECTION_CHANGED",
        );
    }
    let current_success = Ok(json!({"library": "b"}));
    let current_failure = Err(error("CURRENT_LIBRARY_ERROR", "本次库失败结果"));
    for result in [current_success, current_failure] {
        assert_eq!(
            complete_bridge_request(&fixture.state, &b_id, result.clone()),
            result
        );
    }
    assert!(fixture.requests("a").is_empty() && fixture.requests("b").is_empty());
}

#[test]
fn switching_blocks_external_reads_writes_media_and_completions() {
    tauri::async_runtime::block_on(async {
        let fixture = ScopeFixture::new();
        let id = fixture.connection_id();
        fixture.state.switching.store(true, Ordering::SeqCst);
        for value in [ui_request(), request("GET", "/api/v1/projects", None)] {
            assert_code(
                bridge_request(&fixture.state, scoped(value, &id)).await,
                "LIBRARY_SWITCH_PENDING",
            );
        }
        assert_code(
            bridge_media(&fixture.state, ARTIFACT_ID.into(), id.clone()).await,
            "LIBRARY_SWITCH_PENDING",
        );
        for result in [
            Ok(json!({"library": "a"})),
            Err(error("OLD_ERROR", "旧失败")),
        ] {
            assert_code(
                complete_bridge_request(&fixture.state, &id, result),
                "LIBRARY_SWITCH_PENDING",
            );
        }
        assert!(fixture.requests("a").is_empty());
    });
}

#[test]
fn failed_switch_rollback_invalidates_the_previous_connection() {
    tauri::async_runtime::block_on(async {
        let fixture = ScopeFixture::new();
        let old_id = fixture.connection_id();
        let current = fixture.state.launch.lock().unwrap().clone();
        let mut invalid = current.clone();
        invalid.executable = fixture.directory.path().join("missing-control");
        invalid.data_dir = fixture.directory.path().join("failed-b");
        fixture.state.switching.store(true, Ordering::SeqCst);
        let failure = fixture
            .state
            .process
            .lock()
            .unwrap()
            .switch_library(
                &current,
                &invalid,
                &fixture.state.selection_file,
                b"failed-b",
            )
            .unwrap_err();
        fixture.state.switching.store(false, Ordering::SeqCst);
        assert!(failure.contains("已恢复连接原工作库"));
        let recovered_id = fixture.connection_id();
        assert_ne!(old_id, recovered_id);
        assert_code(
            bridge_request(&fixture.state, scoped(ui_request(), &old_id)).await,
            "CONTROL_CONNECTION_CHANGED",
        );
        assert!(fixture.requests("a").is_empty());
        assert_eq!(
            bridge_request(&fixture.state, scoped(ui_request(), &recovered_id))
                .await
                .unwrap()["library"],
            "a"
        );
        assert_eq!(fixture.requests("a").len(), 1);
    });
}

#[test]
fn same_library_crash_restart_rotates_id_but_repeated_start_does_not() {
    tauri::async_runtime::block_on(async {
        let fixture = ScopeFixture::new();
        let launch = fixture.state.launch.lock().unwrap().clone();
        let old_id = fixture.connection_id();
        let repeated = fixture
            .state
            .process
            .lock()
            .unwrap()
            .start(&launch)
            .unwrap();
        assert_eq!(repeated.connection_id.as_deref(), Some(old_id.as_str()));
        let pid = repeated.pid.unwrap();
        // 仅模拟本测试创建并仍由 ControlProcess 持有的子进程崩溃。
        assert_eq!(unsafe { libc::kill(pid as i32, libc::SIGKILL) }, 0);
        let deadline = Instant::now() + Duration::from_secs(3);
        loop {
            if fixture.state.process.lock().unwrap().status().state == "failed" {
                break;
            }
            assert!(Instant::now() < deadline, "夹具子进程未被确认退出");
            std::thread::sleep(Duration::from_millis(10));
        }
        let restarted = fixture
            .state
            .process
            .lock()
            .unwrap()
            .start(&launch)
            .unwrap();
        let new_id = restarted.connection_id.unwrap();
        assert_ne!(old_id, new_id);
        assert_eq!(new_id, fixture.connection_id());
        assert_ne!(restarted.pid, Some(pid));
        assert_code(
            bridge_request(&fixture.state, scoped(ui_request(), &old_id)).await,
            "CONTROL_CONNECTION_CHANGED",
        );
        assert!(fixture.requests("a").is_empty());
        assert_eq!(
            bridge_request(&fixture.state, scoped(ui_request(), &new_id))
                .await
                .unwrap()["library"],
            "a"
        );
    });
}

#[test]
fn trusted_internal_requests_remain_available_during_host_switch() {
    tauri::async_runtime::block_on(async {
        let fixture = ScopeFixture::new();
        fixture.state.switching.store(true, Ordering::SeqCst);
        assert_eq!(
            proxy(&fixture.state, ui_request()).await.unwrap()["library"],
            "a"
        );
        let host = proxy_host(
            &fixture.state,
            request("POST", "/api/v1/host/reconfiguration", Some(json!({}))),
        )
        .await
        .unwrap();
        assert_eq!(host["library"], "a");
        assert_eq!(host["host_authorized"], true);
        assert_eq!(fixture.requests("a").len(), 2);
    });
}
