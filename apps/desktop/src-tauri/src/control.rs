use serde::{Deserialize, Serialize};
use std::{
    fs::{self, OpenOptions},
    io::{BufRead, BufReader, Read, Write},
    net::{SocketAddr, TcpStream},
    path::PathBuf,
    process::{Child, Command, Stdio},
    sync::mpsc,
    thread,
    time::{Duration, Instant},
};

#[derive(Clone)]
pub struct LaunchConfig {
    pub executable: PathBuf,
    pub args: Vec<String>,
    pub cwd: Option<PathBuf>,
    pub data_dir: PathBuf,
}

#[derive(Clone, Serialize, Debug, PartialEq)]
pub struct HostStatus {
    pub state: String,
    pub message: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub pid: Option<u32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub port: Option<u16>,
}

impl HostStatus {
    pub fn stopped(message: impl Into<String>) -> Self {
        Self {
            state: "stopped".into(),
            message: message.into(),
            pid: None,
            port: None,
        }
    }
}

// 会话令牌只留在 Rust 内存中，不能序列化到 WebView。
#[derive(Clone)]
pub struct Connection {
    pub port: u16,
    pub token: String,
    pub host_token: Option<String>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Handshake {
    port: u16,
    token: String,
    pid: u32,
    #[serde(default)]
    host_token: Option<String>,
}

#[derive(Deserialize)]
#[serde(untagged)]
enum StartupResponse {
    Ready(Handshake),
    Failed(StartupFailure),
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct StartupFailure {
    status: StartupFailureStatus,
    code: StartupFailureCode,
    pid: u32,
}

#[derive(Deserialize)]
enum StartupFailureStatus {
    #[serde(rename = "failed")]
    Failed,
}

#[derive(Deserialize)]
enum StartupFailureCode {
    #[serde(rename = "DATABASE_MIGRATION_FAILED")]
    DatabaseMigrationFailed,
}

pub struct ControlProcess {
    child: Option<Child>,
    connection: Option<Connection>,
    status: HostStatus,
}

impl Default for ControlProcess {
    fn default() -> Self {
        Self {
            child: None,
            connection: None,
            status: HostStatus::stopped("本地服务尚未启动。"),
        }
    }
}

impl ControlProcess {
    pub fn switch_library(
        &mut self,
        current: &LaunchConfig,
        next: &LaunchConfig,
        selection_file: &std::path::Path,
        selection: &[u8],
    ) -> Result<HostStatus, String> {
        self.stop();
        let switched = self.start(next).and_then(|status| {
            let stamp = std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap_or_default()
                .as_nanos();
            let temporary =
                selection_file.with_extension(format!("{}-{stamp}.tmp", std::process::id()));
            let persisted = (|| -> std::io::Result<()> {
                let mut file = OpenOptions::new()
                    .write(true)
                    .create_new(true)
                    .open(&temporary)?;
                file.write_all(selection)?;
                file.sync_all()?;
                fs::rename(&temporary, selection_file)?;
                Ok(())
            })();
            if persisted.is_err() {
                let _ = fs::remove_file(temporary);
                return Err("新工作库已连接，但无法保存切换设置。".to_string());
            }
            Ok(status)
        });
        match switched {
            Ok(status) => Ok(status),
            Err(reason) => {
                self.stop();
                match self.start(current) {
                    Ok(_) => Err(format!("{reason} 已恢复连接原工作库。")),
                    Err(_) => Err(format!("{reason} 原工作库暂时未能重连，请点击重新连接。")),
                }
            }
        }
    }

    pub fn start(&mut self, config: &LaunchConfig) -> Result<HostStatus, String> {
        let result = self.start_with_timeout(config, Duration::from_secs(20));
        if let Err(message) = &result {
            self.status = HostStatus {
                state: "failed".into(),
                message: message.clone(),
                pid: None,
                port: None,
            };
        }
        result
    }

    fn start_with_timeout(
        &mut self,
        config: &LaunchConfig,
        timeout: Duration,
    ) -> Result<HostStatus, String> {
        if self.connection().is_some() {
            return Ok(self.status.clone());
        }
        self.stop();
        fs::create_dir_all(&config.data_dir).map_err(|_| "无法创建应用数据目录。")?;
        let log_dir = config.data_dir.join("logs");
        fs::create_dir_all(&log_dir).map_err(|_| "无法创建服务日志目录。")?;
        let mut command = Command::new(&config.executable);
        command
            .args(&config.args)
            .arg("--data-dir")
            .arg(&config.data_dir)
            .args([
                "--port",
                "0",
                "--parent-pid",
                &std::process::id().to_string(),
            ])
            .env("PYTHONUNBUFFERED", "1")
            .stdin(Stdio::null())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());
        if let Some(cwd) = &config.cwd {
            command.current_dir(cwd);
        }
        let mut child = command
            .spawn()
            .map_err(|_| "本地服务无法启动，请检查控制环境或重新安装应用。".to_string())?;
        let pid = child.id();
        let stdout = child.stdout.take().ok_or("无法读取服务启动结果。")?;
        let stderr = child.stderr.take().ok_or("无法读取服务日志。")?;
        let (sender, receiver) = mpsc::sync_channel(1);
        thread::spawn(move || {
            // 首行限制为 4096 字节，避免异常子进程无限写入占满宿主内存。
            let mut reader = BufReader::new(stdout);
            let mut line = Vec::new();
            let result = reader
                .by_ref()
                .take(4097)
                .read_until(b'\n', &mut line)
                .map_err(|_| "服务启动通信中断。".to_string())
                .and_then(|_| {
                    if line.len() > 4096 || !line.ends_with(b"\n") {
                        return Err("服务启动响应格式无效。".into());
                    }
                    serde_json::from_slice::<StartupResponse>(&line)
                        .map_err(|_| "服务启动响应格式无效。".into())
                });
            let _ = sender.send(result);
            // 业务日志应走 stderr；后续 stdout 不进入日志，防止意外输出令牌。
            let _ = std::io::copy(&mut reader, &mut std::io::sink());
        });
        let log_path = log_dir.join("control.log");
        thread::spawn(move || {
            let Ok(mut log) = OpenOptions::new().create(true).append(true).open(log_path) else {
                return;
            };
            let mut reader = BufReader::new(stderr);
            let mut chunk = [0u8; 8192];
            while let Ok(count) = reader.read(&mut chunk) {
                if count == 0 {
                    break;
                }
                let _ = log.write_all(&chunk[..count]);
            }
        });
        self.child = Some(child);
        let result = receiver
            .recv_timeout(timeout)
            .map_err(|_| "本地服务启动超时，可重启服务。".to_string())
            .and_then(|value| value)
            .and_then(|value| {
                let value = match value {
                    StartupResponse::Ready(handshake) => handshake,
                    StartupResponse::Failed(failure) => {
                        if failure.pid != pid {
                            return Err("服务身份校验失败，已停止此服务。".into());
                        }
                        // 不透传异常正文，也不推断此次迁移是否已提交或已有备份。
                        return match (failure.status, failure.code) {
                            (StartupFailureStatus::Failed, StartupFailureCode::DatabaseMigrationFailed) =>
                                Err("数据库迁移失败，运行器未启动。请保留工作库，检查迁移备份与回执后重试。".into()),
                        };
                    }
                };
                if value.pid != pid
                    || value.port == 0
                    || value.token.len() < 32
                    || value.token.len() > 512
                    || !value.token.bytes().all(|byte| byte.is_ascii_graphic())
                    || value.host_token.as_ref().is_some_and(|token| token.len() < 32 || token.len() > 512 || !token.bytes().all(|byte| byte.is_ascii_graphic()))
                {
                    return Err("服务身份校验失败，已停止此服务。".into());
                }
                let deadline = Instant::now() + Duration::from_secs(10);
                let address = SocketAddr::from(([127, 0, 0, 1], value.port));
                while Instant::now() < deadline {
                    if let Some(child) = self.child.as_mut() {
                        if !matches!(child.try_wait(), Ok(None)) {
                            return Err("本地服务在启动完成前退出。".into());
                        }
                    }
                    if let Ok(mut stream) = TcpStream::connect_timeout(&address, Duration::from_millis(100)) {
                        let _ = stream.set_read_timeout(Some(Duration::from_millis(300)));
                        let _ = stream.set_write_timeout(Some(Duration::from_millis(300)));
                        if write!(stream, "GET /health HTTP/1.1\r\nHost: 127.0.0.1:{}\r\nConnection: close\r\n\r\n", value.port).is_ok() {
                            let mut first_line = String::new();
                            if BufReader::new(stream).take(512).read_line(&mut first_line).is_ok() && first_line.split_whitespace().nth(1) == Some("200") {
                                return Ok(value);
                            }
                        }
                    }
                    thread::sleep(Duration::from_millis(50));
                }
                Err("本地服务未能完成健康检查，可重启服务。".into())
            });
        match result {
            Ok(handshake) => {
                self.connection = Some(Connection {
                    port: handshake.port,
                    token: handshake.token,
                    host_token: handshake.host_token,
                });
                self.status = HostStatus {
                    state: "running".into(),
                    message: "本地控制服务已连接。".into(),
                    pid: Some(pid),
                    port: Some(handshake.port),
                };
                Ok(self.status.clone())
            }
            Err(message) => {
                self.stop();
                self.status = HostStatus {
                    state: "failed".into(),
                    message: message.clone(),
                    pid: None,
                    port: None,
                };
                Err(message)
            }
        }
    }

    pub fn status(&mut self) -> HostStatus {
        if let Some(child) = self.child.as_mut() {
            match child.try_wait() {
                Ok(Some(_)) => {
                    self.child = None;
                    self.connection = None;
                    self.status = HostStatus {
                        state: "failed".into(),
                        message: "本地服务已意外退出。任务记录已保留，可以重启服务继续。".into(),
                        pid: None,
                        port: None,
                    };
                }
                Err(_) => {
                    self.connection = None;
                    self.status.state = "failed".into();
                    self.status.message = "无法确认本地服务状态，请重启服务。".into();
                }
                Ok(None) => {}
            }
        }
        self.status.clone()
    }

    pub fn connection(&mut self) -> Option<Connection> {
        self.status();
        self.connection.clone()
    }

    pub fn stop(&mut self) {
        self.connection = None;
        if let Some(mut child) = self.child.take() {
            // 只对仍由 Child 句柄持有、尚未退出的进程发信号；不扫描名称或误杀其他服务。
            if matches!(child.try_wait(), Ok(None)) {
                #[cfg(unix)]
                unsafe {
                    libc::kill(child.id() as i32, libc::SIGTERM);
                }
                let deadline = Instant::now() + Duration::from_secs(8);
                while Instant::now() < deadline {
                    if !matches!(child.try_wait(), Ok(None)) {
                        break;
                    }
                    thread::sleep(Duration::from_millis(40));
                }
                if matches!(child.try_wait(), Ok(None)) {
                    let _ = child.kill();
                }
            }
            let _ = child.wait();
        }
        self.status = HostStatus::stopped("本地服务已停止。");
    }
}

impl Drop for ControlProcess {
    fn drop(&mut self) {
        self.stop();
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn fixture(code: &str) -> (tempfile::TempDir, LaunchConfig) {
        let dir = tempfile::tempdir().unwrap();
        let script = dir.path().join("service.py");
        fs::write(&script, code).unwrap();
        let config = LaunchConfig {
            executable: "/usr/bin/python3".into(),
            args: vec![script.to_string_lossy().into()],
            cwd: None,
            data_dir: dir.path().join("data"),
        };
        (dir, config)
    }

    const HEALTHY: &str = "import os,json\nfrom http.server import HTTPServer,BaseHTTPRequestHandler\nclass Handler(BaseHTTPRequestHandler):\n def do_GET(self):\n  self.send_response(200)\n  self.end_headers()\n def log_message(self,*args): pass\nserver=HTTPServer(('127.0.0.1',0),Handler)\nprint(json.dumps({'port':server.server_port,'pid':os.getpid(),'token':'x'*48}),flush=True)\nserver.serve_forever()\n";

    #[test]
    fn owned_lifecycle_does_not_stop_unrelated_child() {
        let (_dir, config) = fixture(HEALTHY);
        let mut unrelated = Command::new("/bin/sleep").arg("20").spawn().unwrap();
        let mut service = ControlProcess::default();
        let started = service.start(&config).unwrap();
        assert_eq!(started.state, "running");
        assert!(!serde_json::to_string(&started).unwrap().contains("token"));
        assert_eq!(service.start(&config).unwrap().pid, started.pid);
        service.stop();
        assert_eq!(service.status().state, "stopped");
        assert!(unrelated.try_wait().unwrap().is_none());
        unrelated.kill().unwrap();
        unrelated.wait().unwrap();
    }

    #[test]
    fn crash_is_visible_and_restart_uses_new_child() {
        let (_dir, config) = fixture(HEALTHY);
        let mut service = ControlProcess::default();
        let initial = service.start(&config).unwrap().pid.unwrap();
        service.child.as_mut().unwrap().kill().unwrap();
        service.child.as_mut().unwrap().wait().unwrap();
        assert_eq!(service.status().state, "failed");
        assert!(service.connection().is_none());
        let restarted = service.start(&config).unwrap();
        assert_ne!(restarted.pid, Some(initial));
        service.stop();
    }

    #[test]
    fn invalid_identity_and_timeout_are_reaped() {
        let (_dir, config) = fixture("import json,time\nprint(json.dumps({'port':12,'pid':1,'token':'x'*48}),flush=True)\ntime.sleep(20)\n");
        let mut service = ControlProcess::default();
        assert!(service.start(&config).is_err());
        assert!(service.child.is_none());
        assert_eq!(service.status().state, "failed");
        let (_dir2, config2) = fixture("import time\ntime.sleep(20)\n");
        assert!(service
            .start_with_timeout(&config2, Duration::from_millis(100))
            .is_err());
        assert!(service.child.is_none());
    }

    #[test]
    fn switch_library_persists_only_after_success_and_rolls_back_failures() {
        let (dir, current) = fixture(HEALTHY);
        let selection = dir.path().join("selected-library.json");
        fs::write(&selection, b"original").unwrap();
        let mut service = ControlProcess::default();
        service.start(&current).unwrap();
        let mut next = current.clone();
        next.data_dir = dir.path().join("restored");
        let previous_pid = service.status().pid;
        let result = service
            .switch_library(&current, &next, &selection, b"restored")
            .unwrap();
        assert_ne!(result.pid, previous_pid);
        assert_eq!(fs::read(&selection).unwrap(), b"restored");
        let mut invalid = next.clone();
        invalid.executable = dir.path().join("missing-control");
        let failure = service
            .switch_library(&next, &invalid, &selection, b"invalid")
            .unwrap_err();
        assert!(failure.contains("已恢复连接原工作库"));
        assert_eq!(service.status().state, "running");
        assert_eq!(fs::read(&selection).unwrap(), b"restored");
        let missing_parent = dir.path().join("missing-parent/selected.json");
        let failure = service
            .switch_library(&next, &current, &missing_parent, b"unsaved")
            .unwrap_err();
        assert!(failure.contains("已恢复连接原工作库"));
        assert_eq!(service.status().state, "running");
        assert_eq!(fs::read(&selection).unwrap(), b"restored");
        service.stop();
    }

    #[test]
    fn fixture_reconfiguration_restarts_same_library_and_rolls_back_configuration() {
        let (directory, current) = fixture(HEALTHY);
        let settings = directory.path().join("host-settings.json");
        let selected = directory.path().join("selected-library.json");
        fs::write(&selected, b"existing-restored-library").unwrap();
        fs::write(&settings, b"{}").unwrap();
        let mut next = current.clone();
        next.args.extend([
            "--market-fixture-origin".into(),
            "http://127.0.0.1:4321".into(),
        ]);
        let enabled = br#"{"market_fixture_origin":"http://127.0.0.1:4321"}"#;
        let mut service = ControlProcess::default();
        service.start(&current).unwrap();
        let initial = service.status().pid;
        service
            .switch_library(&current, &next, &settings, enabled)
            .unwrap();
        assert_ne!(service.status().pid, initial);
        assert_eq!(current.data_dir, next.data_dir);
        assert_eq!(fs::read(&settings).unwrap(), enabled);
        let mut invalid = next.clone();
        invalid.executable = directory.path().join("invalid-binary");
        assert!(service
            .switch_library(&next, &invalid, &settings, b"uncommitted")
            .is_err());
        assert_eq!(service.status().state, "running");
        assert_eq!(fs::read(&settings).unwrap(), enabled);
        assert!(service
            .switch_library(
                &next,
                &current,
                &directory.path().join("missing/settings.json"),
                b"uncommitted"
            )
            .is_err());
        assert_eq!(service.status().state, "running");
        assert_eq!(fs::read(&settings).unwrap(), enabled);
        service
            .switch_library(
                &next,
                &current,
                &settings,
                br#"{"market_fixture_origin":null}"#,
            )
            .unwrap();
        assert_eq!(
            fs::read(&settings).unwrap(),
            br#"{"market_fixture_origin":null}"#
        );
        assert_eq!(fs::read(&selected).unwrap(), b"existing-restored-library");
        service.stop();
    }

    #[test]
    fn current_success_handshake_accepts_host_token() {
        let (_dir, config) =
            fixture(&HEALTHY.replace("'token':'x'*48", "'token':'x'*48,'host_token':'h'*64"));
        let mut service = ControlProcess::default();
        let status = service.start(&config).unwrap();
        assert_eq!(
            service.connection().unwrap().host_token.as_deref(),
            Some("hhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhh")
        );
        assert!(!serde_json::to_string(&status).unwrap().contains("token"));
        service.stop();
    }

    #[test]
    fn known_migration_failure_is_fixed_and_owned_child_is_reaped() {
        let (dir, config) = fixture("import os,json,time\nfrom pathlib import Path\nPath(__file__).with_suffix('.pid').write_text(str(os.getpid()))\nprint(json.dumps({'status':'failed','code':'DATABASE_MIGRATION_FAILED','pid':os.getpid()}).ljust(4095),flush=True)\ntime.sleep(20)\n");
        let mut service = ControlProcess::default();
        let failure = service.start(&config).unwrap_err();
        assert_eq!(
            failure,
            "数据库迁移失败，运行器未启动。请保留工作库，检查迁移备份与回执后重试。"
        );
        assert_eq!(service.status().state, "failed");
        assert!(service.connection().is_none() && service.child.is_none());
        let pid: i32 = fs::read_to_string(dir.path().join("service.pid"))
            .unwrap()
            .parse()
            .unwrap();
        #[cfg(unix)]
        assert_eq!(unsafe { libc::kill(pid, 0) }, -1);
        assert!(!serde_json::to_string(&service.status())
            .unwrap()
            .contains("token"));
    }

    #[test]
    fn invalid_failure_shapes_identity_and_line_bounds_are_rejected() {
        let cases = [
            ("json.dumps({'status':'failed','code':'UNKNOWN_FAILURE','pid':os.getpid()})", "服务启动响应格式无效。"),
            ("json.dumps({'status':'failed','code':'DATABASE_MIGRATION_FAILED','pid':1})", "服务身份校验失败，已停止此服务。"),
            ("json.dumps({'status':'failed','code':'DATABASE_MIGRATION_FAILED','pid':str(os.getpid())})", "服务启动响应格式无效。"),
            ("json.dumps({'status':'failed','code':'DATABASE_MIGRATION_FAILED','pid':True})", "服务启动响应格式无效。"),
            ("json.dumps({'status':'failed','code':'DATABASE_MIGRATION_FAILED'})", "服务启动响应格式无效。"),
            ("json.dumps({'status':'ready','code':'DATABASE_MIGRATION_FAILED','pid':os.getpid()})", "服务启动响应格式无效。"),
            ("json.dumps({'status':'failed','code':'DATABASE_MIGRATION_FAILED','pid':os.getpid(),'message':'private-token-or-path'})", "服务启动响应格式无效。"),
            ("json.dumps({'status':'failed','code':'DATABASE_MIGRATION_FAILED','pid':os.getpid(),'detail':{'token':'private-token-or-path'}})", "服务启动响应格式无效。"),
            ("json.dumps({'status':'failed','code':'DATABASE_MIGRATION_FAILED','pid':os.getpid(),'port':123,'token':'x'*48})", "服务启动响应格式无效。"),
            ("json.dumps({'port':123,'token':'x'*48,'pid':os.getpid(),'code':'DATABASE_MIGRATION_FAILED'})", "服务启动响应格式无效。"),
            ("'not-json-private-token-or-path'", "服务启动响应格式无效。"),
            ("'['", "服务启动响应格式无效。"),
            ("'x'*4096", "服务启动响应格式无效。"),
            ("json.dumps({'status':'failed','code':'DATABASE_MIGRATION_FAILED','pid':os.getpid()}) + ' '*4096", "服务启动响应格式无效。"),
            ("'{\"status\":\"failed\",\"code\":\"DATABASE_MIGRATION_FAILED\",\"pid\":1,\"pid\":'+str(os.getpid())+'}'", "服务启动响应格式无效。"),
        ];
        for (payload, expected) in cases {
            let code = format!("import os,json,time\nfrom pathlib import Path\nPath(__file__).with_suffix('.pid').write_text(str(os.getpid()))\nprint({payload},flush=True)\ntime.sleep(20)\n");
            let (dir, config) = fixture(&code);
            let mut service = ControlProcess::default();
            assert_eq!(
                service.start(&config).unwrap_err(),
                expected,
                "拒绝报文：{payload}"
            );
            assert!(service.child.is_none() && service.connection().is_none());
            let pid: i32 = fs::read_to_string(dir.path().join("service.pid"))
                .unwrap()
                .parse()
                .unwrap();
            #[cfg(unix)]
            assert_eq!(unsafe { libc::kill(pid, 0) }, -1);
            assert!(!serde_json::to_string(&service.status())
                .unwrap()
                .contains("private"));
        }
        let (_dir, config) = fixture("import os,json,sys\nsys.stdout.write(json.dumps({'status':'failed','code':'DATABASE_MIGRATION_FAILED','pid':os.getpid()}))\nsys.stdout.flush()\n");
        let mut service = ControlProcess::default();
        assert_eq!(
            service.start(&config).unwrap_err(),
            "服务启动响应格式无效。"
        );
        assert!(service.child.is_none());
    }

    #[test]
    fn migration_failure_during_library_switch_restores_original_selection() {
        let (dir, current) = fixture(HEALTHY);
        let (_failed_dir, next) = fixture("import os,json\nprint(json.dumps({'status':'failed','code':'DATABASE_MIGRATION_FAILED','pid':os.getpid()}),flush=True)\nraise SystemExit(1)\n");
        let selection = dir.path().join("selected-library.json");
        fs::write(&selection, b"original").unwrap();
        let mut service = ControlProcess::default();
        let initial = service.start(&current).unwrap().pid;
        let failure = service
            .switch_library(&current, &next, &selection, b"failed-library")
            .unwrap_err();
        assert_eq!(failure, "数据库迁移失败，运行器未启动。请保留工作库，检查迁移备份与回执后重试。 已恢复连接原工作库。");
        assert_eq!(service.status().state, "running");
        assert_ne!(service.status().pid, initial);
        assert!(service.connection().is_some());
        assert_eq!(fs::read(&selection).unwrap(), b"original");
        service.stop();
    }

    #[test]
    #[ignore = "需要已准备好的真实控制服务，由交付验证显式运行"]
    fn real_migration_failure_switch_preserves_evidence_and_reconnects_original() {
        let executable =
            PathBuf::from(std::env::var_os("AILAB_TEST_CONTROL_BINARY").expect("真实控制服务入口"));
        let python = PathBuf::from(
            std::env::var_os("AILAB_TEST_CONTROL_PYTHON").expect("已准备好的 Python"),
        );
        let dir = tempfile::tempdir().unwrap();
        let next_directory = dir.path().join("migration-failure");
        fs::create_dir(&next_directory).unwrap();
        let database = next_directory.join("control.sqlite3");
        // 使用固定 v1 结构和真实索引重名冲突，不替换业务迁移实现。
        let prepared = Command::new(&python).arg("-c").arg(r#"
import sqlite3,sys
with sqlite3.connect(sys.argv[1]) as db:
 db.executescript('''
CREATE TABLE schema_version(version INTEGER PRIMARY KEY);
INSERT INTO schema_version VALUES(1);
CREATE TABLE projects(id TEXT PRIMARY KEY,body TEXT NOT NULL);
CREATE TABLE resources(id TEXT PRIMARY KEY,kind TEXT NOT NULL,project_id TEXT NOT NULL REFERENCES projects(id),body TEXT NOT NULL);
CREATE INDEX resources_project_kind ON resources(project_id,kind);
CREATE TABLE events(attempt_id TEXT NOT NULL REFERENCES resources(id),sequence INTEGER NOT NULL,body TEXT NOT NULL,PRIMARY KEY(attempt_id,sequence));
CREATE TABLE commands(scope TEXT NOT NULL,key TEXT NOT NULL,request_digest TEXT NOT NULL,response TEXT NOT NULL,PRIMARY KEY(scope,key));
CREATE TABLE app_settings(id INTEGER PRIMARY KEY CHECK(id=1),body TEXT NOT NULL);
CREATE INDEX resources_kind ON resources(kind);
''')
"#).arg(&database).status().unwrap();
        assert!(prepared.success());
        let before = fs::read(&database).unwrap();
        let connection_file = dir.path().join("connection.json");
        let current = LaunchConfig {
            executable,
            args: vec![
                "--token-file".into(),
                connection_file.to_string_lossy().into(),
            ],
            cwd: Some(dir.path().into()),
            data_dir: dir.path().join("original"),
        };
        let mut next = current.clone();
        next.data_dir = next_directory.clone();
        let selection = dir.path().join("selected-library.json");
        fs::write(&selection, b"original").unwrap();
        let mut service = ControlProcess::default();
        let initial = service.start(&current).unwrap();
        assert!(service.connection().unwrap().host_token.is_some());
        assert_eq!(
            serde_json::from_slice::<serde_json::Value>(&fs::read(&connection_file).unwrap())
                .unwrap()["pid"],
            initial.pid.unwrap()
        );
        let failure = service
            .switch_library(&current, &next, &selection, b"failed-library")
            .unwrap_err();
        let recovered = service.status();
        assert_eq!(failure, "数据库迁移失败，运行器未启动。请保留工作库，检查迁移备份与回执后重试。 已恢复连接原工作库。");
        assert_eq!(recovered.state, "running");
        assert_ne!(recovered.pid, initial.pid);
        assert_eq!(fs::read(&selection).unwrap(), b"original");
        assert_eq!(fs::read(&database).unwrap(), before);
        assert_eq!(
            serde_json::from_slice::<serde_json::Value>(&fs::read(&connection_file).unwrap())
                .unwrap()["pid"],
            recovered.pid.unwrap()
        );
        let receipts: Vec<_> = fs::read_dir(next_directory.join("migrations"))
            .unwrap()
            .map(|entry| entry.unwrap().path().join("receipt.json"))
            .collect();
        assert_eq!(receipts.len(), 1);
        let receipt: serde_json::Value =
            serde_json::from_slice(&fs::read(&receipts[0]).unwrap()).unwrap();
        assert_eq!(receipt["status"], "failed_rolled_back");
        assert_eq!(receipt["committed"], false);
        let verified = Command::new(&python)
            .arg("-c")
            .arg(
                r#"
import fcntl,hashlib,json,sqlite3,sys
from pathlib import Path
source,receipt_path = map(Path,sys.argv[1:])
receipt = json.loads(receipt_path.read_text())
backup = receipt_path.parent / receipt['backup']['path']
assert hashlib.sha256(backup.read_bytes()).hexdigest() == receipt['backup']['sha256']
assert backup.stat().st_size == receipt['backup']['size']
with sqlite3.connect(source) as original, sqlite3.connect(backup) as saved:
 assert original.execute('SELECT version FROM schema_version').fetchone()[0] == 1
 assert saved.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
 assert list(original.iterdump()) == list(saved.iterdump())
with (source.parent / 'control.lock').open('r+') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX | fcntl.LOCK_NB)
 fcntl.flock(lock,fcntl.LOCK_UN)
"#,
            )
            .arg(&database)
            .arg(&receipts[0])
            .status()
            .unwrap();
        assert!(verified.success());
        let failure_log = fs::read_to_string(next_directory.join("logs/control.log")).unwrap();
        assert!(
            failure_log.contains("sqlite3.OperationalError: index resources_kind already exists")
        );
        assert!(
            failure_log.contains("ailab_control.storage.Fault: 数据库迁移未完成验收，运行器未启动")
        );
        service.stop();
        assert!(service.child.is_none() && service.connection().is_none());
        assert!(!connection_file.exists());
        for pid in [initial.pid.unwrap(), recovered.pid.unwrap()] {
            #[cfg(unix)]
            assert_eq!(unsafe { libc::kill(pid as i32, 0) }, -1);
        }
        if std::env::var_os("AILAB_TEST_PRESERVE_DIRECTORY").is_some() {
            fs::write(dir.path().join("lifecycle-evidence.json"), serde_json::to_vec_pretty(&serde_json::json!({
                "result": "passed", "failure": failure, "original_pid": initial.pid, "recovered_pid": recovered.pid,
                "owned_processes_reaped": true, "connection_file_absent": true, "selection_unchanged": true,
                "failed_database_unchanged": true, "failure_diagnostics_preserved": true, "receipt_status": receipt["status"], "committed": receipt["committed"]
            })).unwrap()).unwrap();
            eprintln!("真实迁移生命周期证据：{}", dir.keep().display());
        }
    }

    #[test]
    #[ignore = "需要已准备好的真实控制服务，由交付验证显式运行"]
    fn real_control_handshake_authentication_and_restart() {
        use std::net::TcpStream;
        let root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../..")
            .canonicalize()
            .unwrap();
        let dir = tempfile::tempdir().unwrap();
        let packaged = std::env::var_os("AILAB_TEST_CONTROL_BINARY").map(PathBuf::from);
        let config = LaunchConfig {
            executable: packaged
                .clone()
                .unwrap_or_else(|| root.join("services/control/.venv/bin/python")),
            args: if packaged.is_some() {
                vec![]
            } else {
                vec!["-m".into(), "ailab_control".into()]
            },
            cwd: Some(if packaged.is_some() {
                dir.path().into()
            } else {
                root.join("services/control")
            }),
            data_dir: dir.path().join("data"),
        };
        let mut service = ControlProcess::default();
        let first = service.start(&config).unwrap();
        let connection = service.connection().unwrap();
        for (authorized, status) in [(true, "200"), (false, "401")] {
            let mut stream = TcpStream::connect(("127.0.0.1", connection.port)).unwrap();
            stream
                .set_read_timeout(Some(Duration::from_secs(5)))
                .unwrap();
            let auth = if authorized {
                format!("Authorization: Bearer {}\r\n", connection.token)
            } else {
                String::new()
            };
            write!(stream, "GET /api/v1/projects HTTP/1.1\r\nHost: 127.0.0.1:{}\r\n{}Connection: close\r\n\r\n", connection.port, auth).unwrap();
            let mut response = String::new();
            stream.read_to_string(&mut response).unwrap();
            assert!(
                response.lines().next().unwrap().contains(status),
                "认证边界状态不符"
            );
            assert!(!response.contains(&connection.token));
        }
        service.child.as_mut().unwrap().kill().unwrap();
        service.child.as_mut().unwrap().wait().unwrap();
        assert_eq!(service.status().state, "failed");
        let second = service.start(&config).unwrap();
        assert_ne!(first.pid, second.pid);
        assert_ne!(connection.token, service.connection().unwrap().token);
        service.stop();
        assert!(TcpStream::connect(("127.0.0.1", second.port.unwrap())).is_err());
    }
}
