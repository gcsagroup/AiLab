//! 用临时 HTTP 控制服务检查连接换代；不接触真实工作库、App 或钥匙串。

use super::*;

const ARTIFACT_ID: &str = "artifact-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";

// 两个服务接受相同的资源编号，故不能依赖 project/task ID 区分工作库。
// 只记录 method/path/body；认证只比较，不写进回执。
const CONTROL_FIXTURE: &str = r#"
import json
import os
import sys
import time
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
        if self.path in ('/api/v1/import-grants', '/api/v1/export-grants'):
            result['grant_id'] = 'grant-from-' + root.name
        if self.path == '/api/v1/settings':
            result.update(revision=7, bundled_worker_available=True, bundled_media_worker_available=True, bundled_audio_worker_available=True)
        status = 200
        overrides = root / 'response-overrides.json'
        if overrides.exists():
            override = json.loads(overrides.read_text()).get(self.command + ' ' + self.path)
            if override:
                result, status = override['body'], override['status']
        held = root / 'hold-response'
        if held.exists() and held.read_text() == self.command + ' ' + self.path:
            (root / 'response-waiting').write_text('ready')
            deadline = time.monotonic() + 5
            while not (root / 'release-response').exists() and time.monotonic() < deadline:
                time.sleep(0.005)
        self.send_json(result, status)
        if held.exists():
            (root / 'response-sent').write_text('sent')

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
            recovery_mode: AtomicBool::new(false),
            recovery_original: Mutex::new(None),
            recovery_writes: AtomicUsize::new(0),
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

#[test]
fn picker_waiting_across_switch_never_grants_the_new_library() {
    tauri::async_runtime::block_on(async {
        for export in [false, true] {
            let fixture = ScopeFixture::new();
            let id = fixture.connection_id();
            let result = select_path_grant(&fixture.state, &id, export, async {
                fixture.switch_to("b");
                Ok(Some(fixture.directory.path().to_path_buf()))
            })
            .await;
            assert!(
                fixture.requests("b").is_empty(),
                "旧选择器向 B 授权：{:?}",
                fixture.requests("b")
            );
            assert_eq!(
                result.err().unwrap()["error"]["code"],
                "CONTROL_CONNECTION_CHANGED"
            );
        }
    });
}

#[test]
fn picker_waiting_across_switch_never_updates_new_python_settings() {
    tauri::async_runtime::block_on(async {
        for field in ["worker_python", "media_python", "audio_python"] {
            let fixture = ScopeFixture::new();
            let id = fixture.connection_id();
            let python = fixture.directory.path().join("python-fixture");
            fs::write(&python, b"never executed").unwrap();
            let result = select_python_environment(&fixture.state, &id, field, async {
                fixture.switch_to("b");
                Ok(Some(python))
            })
            .await;
            assert!(
                fixture.requests("b").is_empty(),
                "旧选择器访问 B settings：{:?}",
                fixture.requests("b")
            );
            assert_code(result.map(|v| v.unwrap()), "CONTROL_CONNECTION_CHANGED");
        }
    });
}

#[test]
fn picker_queued_bundled_environment_never_updates_new_library() {
    tauri::async_runtime::block_on(async {
        let fixture = ScopeFixture::new();
        let id = fixture.connection_id();
        fixture.switch_to("b");
        let result = use_bundled_environment(
            &fixture.state,
            &id,
            "worker_python",
            "bundled_worker_available",
        )
        .await;
        assert!(
            fixture.requests("b").is_empty(),
            "排队旧 bundled 命令访问 B：{:?}",
            fixture.requests("b")
        );
        assert_code(result, "CONTROL_CONNECTION_CHANGED");
    });
}

#[test]
fn picker_current_selection_cancel_error_and_all_environment_fields_work() {
    tauri::async_runtime::block_on(async {
        let fixture = ScopeFixture::new();
        let id = fixture.connection_id();
        let path = fixture.directory.path().to_path_buf();
        for export in [false, true] {
            let chosen = select_path_grant(&fixture.state, &id, export, async {
                Ok(Some(path.clone()))
            })
            .await
            .unwrap()
            .unwrap();
            assert_eq!(chosen.path, path.canonicalize().unwrap().to_string_lossy());
            assert_eq!(chosen.grant_id, "grant-from-a");
            assert!(
                select_path_grant(&fixture.state, &id, export, async { Ok(None) })
                    .await
                    .unwrap()
                    .is_none()
            );
            let failure = select_path_grant(&fixture.state, &id, export, async {
                Err(error("FILE_DIALOG_FAILED", "夹具错误"))
            })
            .await;
            assert_eq!(
                failure.err().unwrap()["error"]["code"],
                "FILE_DIALOG_FAILED"
            );
        }
        let target = path.join("python-real");
        fs::write(&target, b"never executed").unwrap();
        let python = path.join("python-venv");
        std::os::unix::fs::symlink(&target, &python).unwrap();
        for (field, available) in [
            ("worker_python", "bundled_worker_available"),
            ("media_python", "bundled_media_worker_available"),
            ("audio_python", "bundled_audio_worker_available"),
        ] {
            let selected = select_python_environment(&fixture.state, &id, field, async {
                Ok(Some(python.clone()))
            })
            .await
            .unwrap()
            .unwrap();
            assert_eq!(
                selected["body"][field],
                python.to_string_lossy().as_ref(),
                "不得将虚拟环境链接改写成目标程序路径"
            );
            assert_eq!(selected["body"]["expected_revision"], 7);
            assert!(!fixture.state.credential_busy.load(Ordering::SeqCst));
            let bundled = use_bundled_environment(&fixture.state, &id, field, available)
                .await
                .unwrap();
            assert_eq!(bundled["body"][field], Value::Null);
            assert_eq!(bundled["body"]["expected_revision"], 7);
            assert!(
                select_python_environment(&fixture.state, &id, field, async { Ok(None) })
                    .await
                    .unwrap()
                    .is_none()
            );
            assert!(!fixture.state.credential_busy.load(Ordering::SeqCst));
        }
        let requests = fixture.requests("a");
        assert_eq!(requests.len(), 14);
        assert_eq!(requests[0]["path"], "/api/v1/import-grants");
        assert_eq!(requests[1]["path"], "/api/v1/export-grants");
        for pair in requests[2..].chunks_exact(2) {
            assert_eq!(pair[0]["method"], "GET");
            assert_eq!(pair[1]["method"], "PATCH");
        }
    });
}

#[test]
fn picker_expired_cancellation_dialog_failure_and_invalid_paths_are_discarded() {
    tauri::async_runtime::block_on(async {
        for outcome in 0..3 {
            for target in 0..3 {
                let fixture = ScopeFixture::new();
                let id = fixture.connection_id();
                let selection = async {
                    fixture.switch_to("b");
                    match outcome {
                        0 => Ok(None),
                        1 => Err(error("FILE_DIALOG_FAILED", "旧窗口错误")),
                        _ => Ok(Some(fixture.directory.path().join("missing-python"))),
                    }
                };
                let failure = if target == 2 {
                    select_python_environment(&fixture.state, &id, "worker_python", selection)
                        .await
                        .err()
                        .unwrap()
                } else {
                    select_path_grant(&fixture.state, &id, target == 1, selection)
                        .await
                        .err()
                        .unwrap()
                };
                assert_eq!(failure["error"]["code"], "CONTROL_CONNECTION_CHANGED");
                assert!(fixture.requests("a").is_empty() && fixture.requests("b").is_empty());
                assert!(!fixture.state.credential_busy.load(Ordering::SeqCst));
            }
        }
    });
}

#[test]
fn picker_queued_commands_reject_before_polling_dialog_future() {
    tauri::async_runtime::block_on(async {
        let fixture = ScopeFixture::new();
        let id = fixture.connection_id();
        fixture.switch_to("b");
        for target in 0..3 {
            let selection = async {
                panic!("过期 IPC 不得启动窗口 Future");
                #[allow(unreachable_code)]
                Ok(None)
            };
            let failure = if target == 2 {
                select_python_environment(&fixture.state, &id, "worker_python", selection)
                    .await
                    .err()
                    .unwrap()
            } else {
                select_path_grant(&fixture.state, &id, target == 1, selection)
                    .await
                    .err()
                    .unwrap()
            };
            assert_eq!(failure["error"]["code"], "CONTROL_CONNECTION_CHANGED");
        }
        for (field, available) in [
            ("worker_python", "bundled_worker_available"),
            ("media_python", "bundled_media_worker_available"),
            ("audio_python", "bundled_audio_worker_available"),
        ] {
            assert_code(
                use_bundled_environment(&fixture.state, &id, field, available).await,
                "CONTROL_CONNECTION_CHANGED",
            );
        }
        assert!(fixture.requests("b").is_empty());
    });
}

#[test]
fn picker_same_library_restart_also_invalidates_selection() {
    tauri::async_runtime::block_on(async {
        for target in 0..3 {
            let fixture = ScopeFixture::new();
            let id = fixture.connection_id();
            let selection = async {
                let launch = fixture.state.launch.lock().unwrap().clone();
                let mut process = fixture.state.process.lock().unwrap();
                process.stop();
                process.start(&launch).unwrap();
                Ok(Some(fixture.directory.path().to_path_buf()))
            };
            let failure = if target == 2 {
                select_python_environment(&fixture.state, &id, "worker_python", selection)
                    .await
                    .err()
                    .unwrap()
            } else {
                select_path_grant(&fixture.state, &id, target == 1, selection)
                    .await
                    .err()
                    .unwrap()
            };
            assert_ne!(id, fixture.connection_id());
            assert_eq!(failure["error"]["code"], "CONTROL_CONNECTION_CHANGED");
            assert!(fixture.requests("a").is_empty());
        }
    });
}

#[test]
fn picker_environment_preserves_reservation_and_revision_failures() {
    tauri::async_runtime::block_on(async {
        let fixture = ScopeFixture::new();
        let id = fixture.connection_id();
        let guard = reserve_host_change(
            &fixture.state,
            &fixture.state.credential_busy,
            "BUSY",
            "夹具",
        )
        .unwrap();
        assert_code(
            use_bundled_environment(
                &fixture.state,
                &id,
                "worker_python",
                "bundled_worker_available",
            )
            .await,
            "HOST_CONFIGURATION_PENDING",
        );
        assert!(fixture.state.credential_busy.load(Ordering::SeqCst));
        drop(guard);
        assert_code(
            use_bundled_environment(&fixture.state, &id, "worker_python", "missing_available")
                .await,
            "ENVIRONMENT_INVALID",
        );
        assert!(!fixture.state.credential_busy.load(Ordering::SeqCst));
        assert_eq!(fixture.requests("a").len(), 1);
        assert_eq!(fixture.requests("a")[0]["method"], "GET");
        let overrides = fixture.directory.path().join("a/response-overrides.json");
        fs::write(&overrides, json!({"GET /api/v1/settings":{"status":200,"body":{"revision":null,"bundled_worker_available":true}}}).to_string()).unwrap();
        assert_code(
            use_bundled_environment(
                &fixture.state,
                &id,
                "worker_python",
                "bundled_worker_available",
            )
            .await,
            "ENVIRONMENT_INVALID",
        );
        assert!(!fixture.state.credential_busy.load(Ordering::SeqCst));
        assert_eq!(fixture.requests("a").len(), 2, "缺 revision 不得发送 PATCH");
        for method in ["GET", "PATCH"] {
            fs::write(&overrides, json!({format!("{method} /api/v1/settings"):{"status":409,"body":{"error":{"code":"REVISION_CONFLICT"}}}}).to_string()).unwrap();
            assert_code(
                use_bundled_environment(
                    &fixture.state,
                    &id,
                    "worker_python",
                    "bundled_worker_available",
                )
                .await,
                "REVISION_CONFLICT",
            );
            assert!(!fixture.state.credential_busy.load(Ordering::SeqCst));
        }
        assert_eq!(fixture.requests("a").len(), 5);
    });
}

fn wait_for_fixture_file(path: &Path) {
    let deadline = Instant::now() + Duration::from_secs(3);
    while !path.exists() {
        assert!(Instant::now() < deadline, "夹具未产生 {}", path.display());
        std::thread::sleep(Duration::from_millis(5));
    }
}

#[test]
fn picker_late_http_results_are_discarded_and_environment_gate_stays_held() {
    for failing_http in [false, true] {
        for target in 0..6 {
            let fixture = ScopeFixture::new();
            let id = fixture.connection_id();
            let a = fixture.directory.path().join("a");
            let endpoint = match target {
                0 => "POST /api/v1/import-grants",
                1 => "POST /api/v1/export-grants",
                2 | 3 => "GET /api/v1/settings",
                _ => "PATCH /api/v1/settings",
            };
            fs::write(a.join("hold-response"), endpoint).unwrap();
            if failing_http {
                fs::write(
                    a.join("response-overrides.json"),
                    json!({endpoint:{"status":500,"body":{"error":{"code":"OLD_SERVICE_ERROR"}}}})
                        .to_string(),
                )
                .unwrap();
            }
            let python = fixture.directory.path().join("python-fixture");
            fs::write(&python, b"never executed").unwrap();
            std::thread::scope(|scope| {
                let waiting = scope.spawn(|| {
                    tauri::async_runtime::block_on(async {
                        if target < 2 {
                            select_path_grant(&fixture.state, &id, target == 1, async {
                                Ok(Some(fixture.directory.path().to_path_buf()))
                            })
                            .await
                            .map(|value| value.map(|v| json!({"grant_id":v.grant_id})))
                        } else if target % 2 == 0 {
                            select_python_environment(&fixture.state, &id, "worker_python", async {
                                Ok(Some(python.clone()))
                            })
                            .await
                        } else {
                            use_bundled_environment(
                                &fixture.state,
                                &id,
                                "worker_python",
                                "bundled_worker_available",
                            )
                            .await
                            .map(Some)
                        }
                    })
                });
                wait_for_fixture_file(&a.join("response-waiting"));
                if target >= 2 {
                    assert!(fixture.state.credential_busy.load(Ordering::SeqCst));
                    let denied = reserve_host_change(
                        &fixture.state,
                        &fixture.state.switching,
                        "BUSY",
                        "夹具",
                    );
                    assert_eq!(
                        denied.err().unwrap()["error"]["code"],
                        "CREDENTIAL_OPERATION_PENDING"
                    );
                }
                // 将已发送的旧 HTTP 成功结果拦在身份复核锁外，随后换代。
                // 环境命令的普通切库已被门禁拒绝；此处直接更换夹具子进程模拟外部崩溃重连。
                let mut process = fixture.state.process.lock().unwrap();
                fs::write(a.join("release-response"), b"release").unwrap();
                wait_for_fixture_file(&a.join("response-sent"));
                let current = fixture.state.launch.lock().unwrap().clone();
                let mut next = current.clone();
                next.data_dir = fixture.directory.path().join("b");
                process
                    .switch_library(&current, &next, &fixture.state.selection_file, b"b")
                    .unwrap();
                *fixture.state.launch.lock().unwrap() = next;
                drop(process);
                assert_code(
                    waiting.join().unwrap().map(|v| v.unwrap()),
                    "CONTROL_CONNECTION_CHANGED",
                );
            });
            assert!(fixture.requests("b").is_empty());
            assert!(!fixture.state.credential_busy.load(Ordering::SeqCst));
            if target == 2 || target == 3 {
                assert_eq!(
                    fixture.requests("a").len(),
                    1,
                    "旧 GET 返回后不得继续 PATCH"
                );
            }
        }
    }
}

fn recovery_fixture() -> ScopeFixture {
    let mut fixture = ScopeFixture::new();
    fixture.state.process.lock().unwrap().stop();
    let canonical = fixture.state.fallback.data_dir.canonicalize().unwrap();
    fixture.state.fallback.data_dir = canonical.clone();
    fixture.state.launch.lock().unwrap().data_dir = canonical;
    fixture.state.selection_file = fixture
        .directory
        .path()
        .canonicalize()
        .unwrap()
        .join("selection.json");
    fs::write(&fixture.state.selection_file, b"original selector").unwrap();
    let status = recovery::begin(&fixture.state).unwrap();
    assert_eq!(status["recovery_mode"], true);
    fixture
}

#[test]
fn cold_recovery_reuses_session_without_changing_original_selection() {
    let fixture = recovery_fixture();
    let first = fixture.state.launch.lock().unwrap().data_dir.clone();
    let id = fixture.connection_id();
    recovery::begin(&fixture.state).unwrap();
    assert_eq!(id, fixture.connection_id());
    fixture.state.process.lock().unwrap().stop();
    recovery::begin(&fixture.state).unwrap();
    assert_ne!(id, fixture.connection_id());
    assert_eq!(first, fixture.state.launch.lock().unwrap().data_dir);
    assert_eq!(
        fs::read(&fixture.state.selection_file).unwrap(),
        b"original selector"
    );
    assert_eq!(
        recovery::previous_library(&fixture.state, &fixture.state.launch.lock().unwrap()).unwrap(),
        fixture.state.fallback.data_dir
    );
    assert_eq!(
        fs::read_dir(fixture.state.fallback.data_dir.join("recovery-sessions"))
            .unwrap()
            .count(),
        1
    );
}

#[test]
fn cold_recovery_rejects_healthy_library_and_protected_targets() {
    let healthy = ScopeFixture::new();
    assert_code(recovery::begin(&healthy.state), "CONTROL_ALREADY_RUNNING");
    assert!(!healthy
        .state
        .fallback
        .data_dir
        .join("recovery-sessions")
        .exists());
    let fixture = recovery_fixture();
    for path in [
        &fixture.state.fallback.data_dir,
        &fixture.state.launch.lock().unwrap().data_dir,
    ] {
        assert_eq!(
            recovery::target(&fixture.state, path).unwrap_err()["error"]["code"],
            "RECOVERY_TARGET_INVALID"
        );
    }
    let external = fixture.directory.path().canonicalize().unwrap();
    assert!(recovery::target(&fixture.state, &external).is_ok());
    let plan = request(
        "POST",
        "/api/v1/restore-plans",
        Some(json!({"target_dir": fixture.state.fallback.data_dir})),
    );
    assert!(recovery::request(&fixture.state, &plan, false).is_err());
}

#[test]
fn cold_recovery_blocks_normal_bridge_media_and_environment_before_side_effects() {
    tauri::async_runtime::block_on(async {
        let fixture = recovery_fixture();
        let id = fixture.connection_id();
        let scratch = fixture.state.launch.lock().unwrap().data_dir.clone();
        for path in ["/api/v1/projects", "/api/v1/settings", "/api/v1/ui-context"] {
            assert_code(
                bridge_request(&fixture.state, scoped(request("GET", path, None), &id)).await,
                "RECOVERY_ONLY",
            );
        }
        assert_code(
            bridge_media(&fixture.state, ARTIFACT_ID.into(), id.clone()).await,
            "RECOVERY_ONLY",
        );
        let picked = AtomicBool::new(false);
        let result = select_python_environment(&fixture.state, &id, "worker_python", async {
            picked.store(true, Ordering::SeqCst);
            Ok(None)
        })
        .await;
        assert_code(result.map(|v| json!(v)), "RECOVERY_ONLY");
        assert!(!picked.load(Ordering::SeqCst));
        assert!(!scratch.join("requests.jsonl").exists());
        bridge_request(
            &fixture.state,
            scoped(request("GET", "/api/v1/restores", None), &id),
        )
        .await
        .unwrap();
    });
}

#[test]
fn cold_recovery_copy_excludes_exit_switch_restart_and_other_copy() {
    let fixture = recovery_fixture();
    let request = request("POST", "/api/v1/restores", Some(json!({})));
    let guard = recovery::reserve_write(&fixture.state, &request).unwrap();
    assert_eq!(fixture.state.recovery_writes.load(Ordering::SeqCst), 1);
    assert!(recovery::reserve_write(&fixture.state, &request).is_err());
    assert!(reserve_host_change(&fixture.state, &fixture.state.switching, "BUSY", "busy").is_err());
    assert!(reserve_host_change(
        &fixture.state,
        &fixture.state.credential_busy,
        "BUSY",
        "busy"
    )
    .is_err());
    assert!(!fixture.state.switching.load(Ordering::SeqCst));
    drop(guard);
    assert_eq!(fixture.state.recovery_writes.load(Ordering::SeqCst), 0);
    let (id, receiver) = fixture
        .state
        .exit_preparation
        .lock()
        .unwrap()
        .begin(Duration::from_secs(5))
        .unwrap();
    assert!(recovery::reserve_write(&fixture.state, &request).is_err());
    fixture
        .state
        .exit_preparation
        .lock()
        .unwrap()
        .finish(id, receiver.try_recv().ok());
    assert!(recovery::reserve_write(&fixture.state, &request).is_ok());
}

#[test]
fn cold_recovery_stop_requires_backend_idle_even_after_request_has_returned() {
    tauri::async_runtime::block_on(async {
        let fixture = recovery_fixture();
        let scratch = fixture.state.launch.lock().unwrap().data_dir.clone();
        let overrides = scratch.join("response-overrides.json");
        fs::write(&overrides, json!({"POST /api/v1/host/reconfiguration": {"status":409,"body":{"error":{"code":"HOST_RECONFIGURATION_BUSY"}}}}).to_string()).unwrap();
        assert_eq!(fixture.state.recovery_writes.load(Ordering::SeqCst), 0);
        assert!(prepare_recovery_stop(&fixture.state).await.is_err());
        assert_eq!(
            fixture.state.process.lock().unwrap().status().state,
            "running"
        );
        let requests = fs::read_to_string(scratch.join("requests.jsonl")).unwrap();
        assert!(requests.contains("DELETE"));
        fs::write(
            &overrides,
            json!({"POST /api/v1/host/reconfiguration": {"status":200,"body":{"ready":true}}})
                .to_string(),
        )
        .unwrap();
        assert!(prepare_recovery_stop(&fixture.state).await.is_ok());
    });
}

#[test]
fn cold_recovery_switch_keeps_session_on_failure_and_commits_original_parent_on_success() {
    let fixture = recovery_fixture();
    let current = fixture.state.launch.lock().unwrap().clone();
    let mut broken = current.clone();
    broken.executable = fixture.directory.path().join("missing-executable");
    broken.data_dir = fixture.directory.path().join("failed-restored");
    let result = fixture
        .state
        .process
        .lock()
        .unwrap()
        .switch_library_checked(
            &current,
            &broken,
            &fixture.state.selection_file,
            b"new",
            || Ok(()),
            || recovery::verify_workspace(&fixture.state).map_err(|e| e.to_string()),
        );
    assert!(result.is_err());
    assert!(fixture.state.recovery_mode.load(Ordering::SeqCst));
    assert_eq!(
        fixture.state.process.lock().unwrap().status().state,
        "running"
    );
    assert_eq!(
        fs::read(&fixture.state.selection_file).unwrap(),
        b"original selector"
    );
    let mut restored = current.clone();
    restored.data_dir = fixture.directory.path().join("healthy-restored");
    let selection = LibrarySelection {
        data_dir: restored.data_dir.clone(),
        previous_data_dir: recovery::previous_library(&fixture.state, &current).unwrap(),
        restore_id: format!("restore-{}", "a".repeat(32)),
    };
    fixture
        .state
        .process
        .lock()
        .unwrap()
        .switch_library_checked(
            &current,
            &restored,
            &fixture.state.selection_file,
            &serde_json::to_vec(&selection).unwrap(),
            || recovery::verify_selection(&fixture.state).map_err(|e| e.to_string()),
            || recovery::verify_workspace(&fixture.state).map_err(|e| e.to_string()),
        )
        .unwrap();
    *fixture.state.launch.lock().unwrap() = restored;
    recovery::complete(&fixture.state).unwrap();
    assert!(!fixture.state.recovery_mode.load(Ordering::SeqCst));
    let saved: Value =
        serde_json::from_slice(&fs::read(&fixture.state.selection_file).unwrap()).unwrap();
    assert_eq!(
        saved["previous_data_dir"],
        fixture.state.fallback.data_dir.to_string_lossy().as_ref()
    );
    assert!(recovery::require_normal(&fixture.state).is_ok());
}

#[test]
fn cold_recovery_rechecks_selector_after_new_service_started_and_rolls_back() {
    let fixture = recovery_fixture();
    let current = fixture.state.launch.lock().unwrap().clone();
    let mut next = current.clone();
    next.data_dir = fixture.directory.path().join("new-service");
    let result = fixture
        .state
        .process
        .lock()
        .unwrap()
        .switch_library_checked(
            &current,
            &next,
            &fixture.state.selection_file,
            b"overwrite",
            || {
                fs::write(&fixture.state.selection_file, b"external selection").unwrap();
                recovery::verify_selection(&fixture.state).map_err(|e| e.to_string())
            },
            || recovery::verify_workspace(&fixture.state).map_err(|e| e.to_string()),
        );
    assert!(result.is_err());
    assert_eq!(
        fs::read(&fixture.state.selection_file).unwrap(),
        b"external selection"
    );
    assert!(fixture.state.recovery_mode.load(Ordering::SeqCst));
    assert_eq!(
        fixture.state.process.lock().unwrap().status().state,
        "running"
    );
}
