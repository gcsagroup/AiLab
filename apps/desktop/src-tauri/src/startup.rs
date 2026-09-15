//! 本机首屏计时：一次启动只保留第一次可见首屏回执，不记录用户内容。

use serde::{Deserialize, Serialize};
#[cfg(unix)]
use std::os::unix::fs::OpenOptionsExt;
use std::{
    fs::{self, OpenOptions},
    io::Write,
    path::PathBuf,
    time::{Instant, SystemTime, UNIX_EPOCH},
};

#[derive(Clone, Copy, Deserialize, Serialize, Debug, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum FirstView {
    EmptyLibrary,
    ProjectHome,
}

#[derive(Clone, Deserialize, Serialize, Debug, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum FrontendStage {
    FrontendMounted,
    HostRunningObserved,
    HostDisconnectedObserved,
    ProjectsStarted,
    ProjectsReady,
    ResourcesStarted,
    ResourcesReady,
    EnvironmentStarted,
    CapabilitiesReady,
    DevicesReady,
    AllConditionsReady,
    ConditionsNotReady,
    Visible,
    Hidden,
    FirstAnimationFrame,
    SecondAnimationFrame,
}

#[derive(Clone, Deserialize, Serialize, Debug, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct FrontendEvent {
    stage: FrontendStage,
    at_ms: f64,
}

#[derive(Clone, Deserialize, Serialize, Debug, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct FrontendPhases {
    time_origin_unix_ms: f64,
    events: Vec<FrontendEvent>,
    omitted_events: u64,
}

impl FrontendPhases {
    fn validate(&self) -> Result<(), String> {
        if !self.time_origin_unix_ms.is_finite() || self.time_origin_unix_ms <= 0.0
            || self.events.is_empty() || self.events.len() > 64
            || self.events.iter().any(|event| !event.at_ms.is_finite() || event.at_ms < 0.0)
            || self.events.windows(2).any(|pair| pair[0].at_ms > pair[1].at_ms)
        {
            return Err("前端启动分段计时无效。".into());
        }
        Ok(())
    }
}

#[derive(Clone, Serialize, Debug, PartialEq)]
pub struct StartupReceipt {
    schema_version: &'static str,
    app_version: String,
    app_build: u64,
    pub pid: u32,
    pub control_pid: u32,
    pub view: FirstView,
    pub host_to_first_frame_ms: f64,
    pub reported_at_unix_ms: u128,
    scope: &'static str,
}

pub struct StartupMetrics {
    started: Instant,
    receipt_path: PathBuf,
    receipt: Option<StartupReceipt>,
    control_ready: Option<(u32, f64)>,
}

impl StartupMetrics {
    pub fn new(started: Instant, receipt_path: PathBuf) -> Self {
        Self {
            started,
            receipt_path,
            receipt: None,
            control_ready: None,
        }
    }

    pub fn mark_control_ready(&mut self, pid: u32) {
        if self.receipt.is_none() {
            self.control_ready = Some((pid, self.started.elapsed().as_secs_f64() * 1000.0));
        }
    }

    pub fn record_with_phases(
        &mut self,
        view: FirstView,
        control_pid: u32,
        frontend: Option<FrontendPhases>,
    ) -> Result<StartupReceipt, String> {
        let already_recorded = self.receipt.is_some();
        let receipt = self.record(view, control_pid)?;
        if !already_recorded {
            if let Some(frontend) = frontend {
                // 分段失败不撤销原首屏回执；验收须独立检查两份文件与进程身份。
                frontend.validate()?;
                let control_ready = self.control_ready.filter(|(pid, _)| *pid == control_pid).map(|(_, at)| at);
                let phases = serde_json::json!({
                    "schema_version": "ailab-startup-phases-v1",
                    "receipt": receipt,
                    "host_control_ready_ms": control_ready,
                    "frontend": frontend,
                    "scope": "宿主阶段采用 run 入口起的 Instant；前端阶段采用同页 performance.now。仅用壁钟近似关联两条时间轴，不能当作统一单调时钟。事件截断或阶段缺失不补零，原首屏就绪定义不变。",
                });
                self.publish(&self.receipt_path.with_file_name("startup-phases-latest.json"), &phases)?;
            }
        }
        Ok(receipt)
    }

    pub fn record(&mut self, view: FirstView, control_pid: u32) -> Result<StartupReceipt, String> {
        if let Some(receipt) = &self.receipt {
            return Ok(receipt.clone());
        }
        let version: serde_json::Value = serde_json::from_str(include_str!(concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/../../../scripts/desktop/version.json"
        )))
        .map_err(|_| "包内版本信息无效。")?;
        let recorded_at = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map_err(|_| "本机时间无效。")?;
        let receipt = StartupReceipt {
            schema_version: "ailab-first-frame-v1",
            app_version: version["version"].as_str().ok_or("包内版本信息缺失。")?.into(),
            app_build: version["build"].as_u64().ok_or("包内构建编号缺失。")?,
            pid: std::process::id(), control_pid, view,
            host_to_first_frame_ms: self.started.elapsed().as_secs_f64() * 1000.0,
            reported_at_unix_ms: recorded_at.as_millis(),
            scope: "宿主 run 入口至可见首屏数据和环境完成后的双动画帧回调；不含操作系统创建进程前的启动耗时。",
        };
        self.publish(&self.receipt_path, &receipt)?;
        self.receipt = Some(receipt.clone());
        Ok(receipt)
    }

    fn publish(&self, path: &std::path::Path, value: &impl Serialize) -> Result<(), String> {
        let parent = path.parent().ok_or("首屏计时目录无效。")?;
        fs::create_dir_all(parent).map_err(|_| "无法创建首屏计时目录。")?;
        let recorded_at = SystemTime::now().duration_since(UNIX_EPOCH).map_err(|_| "本机时间无效。")?;
        let temporary = parent.join(format!(
            ".startup-{}-{}.tmp",
            std::process::id(),
            recorded_at.as_nanos()
        ));
        let result = (|| -> Result<(), Box<dyn std::error::Error>> {
            let mut options = OpenOptions::new();
            options.write(true).create_new(true);
            #[cfg(unix)]
            options.mode(0o600);
            let mut file = options.open(&temporary)?;
            file.write_all(&serde_json::to_vec(value)?)?;
            file.sync_all()?;
            fs::rename(&temporary, path)?;
            Ok(())
        })();
        if result.is_err() {
            let _ = fs::remove_file(&temporary);
            return Err("无法保存首屏计时回执。".into());
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn frontend() -> FrontendPhases {
        serde_json::from_value(serde_json::json!({
            "time_origin_unix_ms": 1000000.0,
            "events": [
                {"stage": "frontend_mounted", "at_ms": 1.0},
                {"stage": "all_conditions_ready", "at_ms": 2.0},
                {"stage": "second_animation_frame", "at_ms": 3.0}
            ],
            "omitted_events": 0
        })).unwrap()
    }

    #[test]
    fn phases_bind_to_first_receipt_and_current_control_without_overwriting() {
        let root = tempfile::tempdir().unwrap();
        let path = root.path().join("startup-latest.json");
        let detail_path = root.path().join("startup-phases-latest.json");
        let mut metrics = StartupMetrics::new(Instant::now(), path.clone());
        metrics.mark_control_ready(40);
        metrics.mark_control_ready(42);
        let first = metrics.record_with_phases(FirstView::ProjectHome, 42, Some(frontend())).unwrap();
        let bytes = fs::read(&detail_path).unwrap();
        let detail: serde_json::Value = serde_json::from_slice(&bytes).unwrap();
        assert_eq!(detail["receipt"], serde_json::from_slice::<serde_json::Value>(&fs::read(path).unwrap()).unwrap());
        assert_eq!(detail["schema_version"], "ailab-startup-phases-v1");
        assert!(detail["host_control_ready_ms"].as_f64().unwrap() <= first.host_to_first_frame_ms);
        metrics.mark_control_ready(43);
        assert_eq!(metrics.record_with_phases(FirstView::EmptyLibrary, 43, Some(frontend())).unwrap(), first);
        assert_eq!(fs::read(&detail_path).unwrap(), bytes);
        assert_eq!(fs::read_dir(root.path()).unwrap().count(), 2);
        #[cfg(unix)] {
            use std::os::unix::fs::PermissionsExt;
            assert_eq!(fs::metadata(detail_path).unwrap().permissions().mode() & 0o777, 0o600);
        }
    }

    #[test]
    fn unavailable_control_stage_is_null_and_phase_failure_keeps_first_receipt() {
        let root = tempfile::tempdir().unwrap();
        let path = root.path().join("startup-latest.json");
        let detail_path = root.path().join("startup-phases-latest.json");
        let mut metrics = StartupMetrics::new(Instant::now(), path.clone());
        metrics.mark_control_ready(40);
        metrics.record_with_phases(FirstView::EmptyLibrary, 42, Some(frontend())).unwrap();
        let detail: serde_json::Value = serde_json::from_slice(&fs::read(&detail_path).unwrap()).unwrap();
        assert!(detail["host_control_ready_ms"].is_null());
        fs::remove_file(&detail_path).unwrap();
        fs::create_dir(&detail_path).unwrap();
        fs::write(detail_path.join("preserved"), b"keep").unwrap();
        let mut later = StartupMetrics::new(Instant::now(), path.clone());
        assert!(later.record_with_phases(FirstView::ProjectHome, 50, Some(frontend())).is_err());
        let receipt: serde_json::Value = serde_json::from_slice(&fs::read(&path).unwrap()).unwrap();
        assert_eq!(receipt["control_pid"], 50);
        assert_eq!(receipt["schema_version"], "ailab-first-frame-v1");
        assert_eq!(fs::read(detail_path.join("preserved")).unwrap(), b"keep");
        assert_eq!(fs::read_dir(root.path()).unwrap().count(), 2);
    }

    #[test]
    fn phase_input_rejects_unknown_content_unbounded_and_invalid_clocks() {
        let mut value = serde_json::to_value(frontend()).unwrap();
        value["events"][0]["stage"] = serde_json::json!("user_text");
        assert!(serde_json::from_value::<FrontendPhases>(value).is_err());
        let mut value = serde_json::to_value(frontend()).unwrap();
        value["events"][0]["content"] = serde_json::json!("not accepted");
        assert!(serde_json::from_value::<FrontendPhases>(value).is_err());
        for clock in [f64::NAN, f64::INFINITY, -1.0] {
            let mut detail = frontend(); detail.events[0].at_ms = clock;
            assert!(detail.validate().is_err());
        }
        let mut detail = frontend(); detail.events[1].at_ms = 0.0;
        assert!(detail.validate().is_err());
        let mut detail = frontend(); detail.events = vec![detail.events[0].clone(); 65];
        assert!(detail.validate().is_err());
        detail.events.truncate(64); detail.omitted_events = 100;
        assert!(detail.validate().is_ok());
    }

    #[test]
    fn first_visible_frame_is_retained_across_later_calls() {
        let root = tempfile::tempdir().unwrap();
        let path = root.path().join("startup-latest.json");
        let mut metrics = StartupMetrics::new(Instant::now(), path.clone());
        let first = metrics.record(FirstView::ProjectHome, 42).unwrap();
        let bytes = fs::read(&path).unwrap();
        assert_eq!(metrics.record(FirstView::EmptyLibrary, 43).unwrap(), first);
        assert_eq!(fs::read(path).unwrap(), bytes);
        assert!(first.host_to_first_frame_ms.is_finite());
    }

    #[test]
    fn published_receipt_has_only_fixed_timing_fields_and_private_mode() {
        let root = tempfile::tempdir().unwrap();
        let path = root.path().join("startup-latest.json");
        fs::write(&path, b"old receipt").unwrap();
        let mut metrics = StartupMetrics::new(Instant::now(), path.clone());
        metrics.record(FirstView::EmptyLibrary, 51).unwrap();
        let value: serde_json::Value = serde_json::from_slice(&fs::read(&path).unwrap()).unwrap();
        let mut fields: Vec<_> = value
            .as_object()
            .unwrap()
            .keys()
            .map(String::as_str)
            .collect();
        fields.sort();
        assert_eq!(
            fields,
            [
                "app_build",
                "app_version",
                "control_pid",
                "host_to_first_frame_ms",
                "pid",
                "reported_at_unix_ms",
                "schema_version",
                "scope",
                "view"
            ]
        );
        assert_eq!(fs::read_dir(root.path()).unwrap().count(), 1);
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            assert_eq!(
                fs::metadata(path).unwrap().permissions().mode() & 0o777,
                0o600
            );
        }
    }

    #[test]
    fn unsupported_view_is_rejected_and_failed_publish_can_retry() {
        assert!(serde_json::from_str::<FirstView>("\"running_model\"").is_err());
        let root = tempfile::tempdir().unwrap();
        let parent = root.path().join("later");
        fs::write(&parent, b"preserve original").unwrap();
        let mut metrics = StartupMetrics::new(Instant::now(), parent.join("startup-latest.json"));
        assert!(metrics.record(FirstView::ProjectHome, 61).is_err());
        assert_eq!(fs::read(&parent).unwrap(), b"preserve original");
        fs::remove_file(&parent).unwrap();
        fs::create_dir(&parent).unwrap();
        assert_eq!(
            metrics
                .record(FirstView::ProjectHome, 61)
                .unwrap()
                .control_pid,
            61
        );
    }
}
