//! 原库无法启动时，只在独立工作区运行既有备份恢复器。

use super::{
    configure_launch_fixture, described_status, error, ApiRequest, HostState, LaunchConfig,
};
use serde_json::{json, Value};
use std::{
    fs::{self, File, OpenOptions},
    io::{Read, Write},
    path::{Component, Path, PathBuf},
    sync::atomic::Ordering,
};

#[derive(Debug, PartialEq, Eq)]
struct FileIdentity {
    #[cfg(unix)]
    device: u64,
    #[cfg(unix)]
    inode: u64,
    #[cfg(unix)]
    mode: u32,
    #[cfg(unix)]
    owner: (u32, u32),
}

impl FileIdentity {
    fn from_metadata(metadata: &fs::Metadata) -> Self {
        #[cfg(unix)]
        use std::os::unix::fs::MetadataExt;
        Self {
            #[cfg(unix)]
            device: metadata.dev(),
            #[cfg(unix)]
            inode: metadata.ino(),
            #[cfg(unix)]
            mode: metadata.mode(),
            #[cfg(unix)]
            owner: (metadata.uid(), metadata.gid()),
        }
    }
}

#[derive(Debug, PartialEq, Eq)]
struct FileSnapshot {
    identity: FileIdentity,
    modified: Option<std::time::SystemTime>,
    #[cfg(unix)]
    changed: (i64, i64),
    bytes: Vec<u8>,
}

// 只读取小型身份文件，绝不读取原工作数据库。缺失与读取失败必须区分。
fn snapshot_file(path: &Path) -> Result<Option<FileSnapshot>, Value> {
    let invalid = || {
        error(
            "RECOVERY_IDENTITY_INVALID",
            "恢复身份文件已变化或不是有效的普通文件；未继续操作。",
        )
    };
    let metadata = match fs::symlink_metadata(path) {
        Ok(metadata) => metadata,
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(_) => return Err(invalid()),
    };
    if !metadata.is_file() || metadata.file_type().is_symlink() || metadata.len() > 64 * 1024 {
        return Err(invalid());
    }
    let mut options = OpenOptions::new();
    options.read(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK);
    }
    let mut file = options.open(path).map_err(|_| invalid())?;
    let opened = file.metadata().map_err(|_| invalid())?;
    if !opened.is_file()
        || FileIdentity::from_metadata(&opened) != FileIdentity::from_metadata(&metadata)
    {
        return Err(invalid());
    }
    let mut bytes = Vec::new();
    Read::by_ref(&mut file)
        .take(64 * 1024 + 1)
        .read_to_end(&mut bytes)
        .map_err(|_| invalid())?;
    let after = file.metadata().map_err(|_| invalid())?;
    #[cfg(unix)]
    use std::os::unix::fs::MetadataExt;
    if bytes.len() > 64 * 1024
        || after.len() != bytes.len() as u64
        || opened.modified().ok() != after.modified().ok()
        || FileIdentity::from_metadata(&opened) != FileIdentity::from_metadata(&after)
        || fs::symlink_metadata(path).map_or(true, |m| {
            FileIdentity::from_metadata(&m) != FileIdentity::from_metadata(&after)
        })
    {
        return Err(invalid());
    }
    #[cfg(unix)]
    if (opened.ctime(), opened.ctime_nsec()) != (after.ctime(), after.ctime_nsec()) {
        return Err(invalid());
    }
    Ok(Some(FileSnapshot {
        identity: FileIdentity::from_metadata(&after),
        modified: after.modified().ok(),
        #[cfg(unix)]
        changed: (after.ctime(), after.ctime_nsec()),
        bytes,
    }))
}

pub(super) struct Session {
    original: LaunchConfig,
    workspace: PathBuf,
    // 目录的 mtime 会随日志/数据库正常改变，只绑定实体与权限。
    directories: Vec<(PathBuf, FileIdentity)>,
    receipt: FileSnapshot,
    selector: Option<FileSnapshot>,
}

impl Session {
    fn capture(
        original: LaunchConfig,
        workspace: PathBuf,
        selector: Option<FileSnapshot>,
    ) -> Result<Self, Value> {
        let workspace = ordinary_directory(&workspace)?;
        let directories = workspace
            .ancestors()
            .take(3)
            .map(|path| {
                fs::symlink_metadata(path)
                    .map(|metadata| (path.to_owned(), FileIdentity::from_metadata(&metadata)))
                    .map_err(|_| error("RECOVERY_IDENTITY_INVALID", "无法保存恢复目录身份。"))
            })
            .collect::<Result<Vec<_>, _>>()?;
        let receipt = snapshot_file(&workspace.join("recovery-session.json"))?
            .ok_or_else(|| error("RECOVERY_IDENTITY_INVALID", "恢复会话回执缺失。"))?;
        let expected = json!({"schema_version":"ailab-recovery-session-v1", "original_data_dir":original.data_dir, "recovery_data_dir":workspace});
        if serde_json::from_slice::<Value>(&receipt.bytes)
            .ok()
            .as_ref()
            != Some(&expected)
        {
            return Err(error(
                "RECOVERY_IDENTITY_INVALID",
                "恢复会话回执与当前工作区不符。",
            ));
        }
        Ok(Self {
            original,
            workspace,
            directories,
            receipt,
            selector,
        })
    }

    fn verify_workspace(&self) -> Result<(), Value> {
        if ordinary_directory(&self.workspace)? != self.workspace
            || self.directories.iter().any(|(path, expected)| {
                fs::symlink_metadata(path).map_or(true, |m| {
                    !m.is_dir()
                        || m.file_type().is_symlink()
                        || &FileIdentity::from_metadata(&m) != expected
                })
            })
            || snapshot_file(&self.workspace.join("recovery-session.json"))?.as_ref()
                != Some(&self.receipt)
        {
            return Err(error(
                "RECOVERY_WORKSPACE_CHANGED",
                "独立恢复工作区身份已变化；未启动其他目录，请保留现场。",
            ));
        }
        Ok(())
    }

    fn verify_selection(&self, path: &Path) -> Result<(), Value> {
        ordinary_directory(
            path.parent()
                .ok_or_else(|| error("RECOVERY_SELECTION_CHANGED", "工作库选择路径无效。"))?,
        )?;
        // profile 也在目录身份集合中；核验时不触碰原数据库。
        if self.directories.iter().skip(2).any(|(p, expected)| {
            fs::symlink_metadata(p).map_or(true, |m| &FileIdentity::from_metadata(&m) != expected)
        }) || snapshot_file(path)? != self.selector
        {
            return Err(error(
                "RECOVERY_SELECTION_CHANGED",
                "原工作库选择已在恢复期间变化，未覆盖新的选择；请保留恢复结果。",
            ));
        }
        Ok(())
    }
}

pub(super) fn verify_workspace(state: &HostState) -> Result<(), Value> {
    if !state.recovery_mode.load(Ordering::SeqCst) {
        return Ok(());
    }
    let session = state
        .recovery_original
        .lock()
        .map_err(|_| error("HOST_STATE_ERROR", "无法读取恢复工作区身份。"))?;
    session
        .as_ref()
        .ok_or_else(|| error("HOST_STATE_ERROR", "恢复会话身份缺失。"))?
        .verify_workspace()
}

pub(super) fn verify_selection(state: &HostState) -> Result<(), Value> {
    if !state.recovery_mode.load(Ordering::SeqCst) {
        return Ok(());
    }
    let session = state
        .recovery_original
        .lock()
        .map_err(|_| error("HOST_STATE_ERROR", "无法读取原选择身份。"))?;
    session
        .as_ref()
        .ok_or_else(|| error("HOST_STATE_ERROR", "恢复会话身份缺失。"))?
        .verify_selection(&state.selection_file)
}

pub(super) struct WriteGuard<'a>(&'a HostState);

impl Drop for WriteGuard<'_> {
    fn drop(&mut self) {
        self.0.recovery_writes.fetch_sub(1, Ordering::SeqCst);
    }
}

pub(super) fn reserve_write<'a>(
    state: &'a HostState,
    request: &ApiRequest,
) -> Result<Option<WriteGuard<'a>>, Value> {
    let path = request.path.split('?').next().unwrap_or("");
    if !state.recovery_mode.load(Ordering::SeqCst)
        || request.method != "POST"
        || !matches!(path, "/api/v1/restore-plans" | "/api/v1/restores")
    {
        return Ok(None);
    }
    // 与退出和切库共用锁，防止检查完成后、复制开始前被停机。
    let preparation = state
        .exit_preparation
        .lock()
        .map_err(|_| error("HOST_STATE_ERROR", "无法读取退出状态。"))?;
    if preparation.is_pending() || state.exiting.load(Ordering::SeqCst) {
        return Err(error(
            "EXIT_PREPARATION_PENDING",
            "正在准备退出，请完成后重试恢复。",
        ));
    }
    if state.switching.load(Ordering::SeqCst) {
        return Err(error(
            "LIBRARY_SWITCH_PENDING",
            "正在切换恢复工作区，请稍候。",
        ));
    }
    if state
        .recovery_writes
        .compare_exchange(0, 1, Ordering::SeqCst, Ordering::SeqCst)
        .is_err()
    {
        return Err(error("RECOVERY_BUSY", "正在校验或恢复备份，请等待完成。"));
    }
    Ok(Some(WriteGuard(state)))
}

pub(super) fn require_normal(state: &HostState) -> Result<(), Value> {
    if state.recovery_mode.load(Ordering::SeqCst) {
        return Err(error(
            "RECOVERY_ONLY",
            "当前只允许从备份恢复；切换到已核实的工作库后再操作。",
        ));
    }
    Ok(())
}

fn ordinary_directory(path: &Path) -> Result<PathBuf, Value> {
    if !path.is_absolute()
        || path.components().any(|p| matches!(p, Component::ParentDir))
        || path.ancestors().any(|p| {
            fs::symlink_metadata(p).map_or(true, |m| !m.is_dir() || m.file_type().is_symlink())
        })
    {
        return Err(error(
            "RECOVERY_PATH_INVALID",
            "恢复目录必须为可访问的普通目录，不能包含链接。",
        ));
    }
    path.canonicalize()
        .map_err(|_| error("RECOVERY_PATH_INVALID", "无法核实恢复目录。"))
}

fn create_workspace(profile: &Path, original: &Path) -> Result<PathBuf, Value> {
    let profile = ordinary_directory(profile)?;
    let parent = profile.join("recovery-sessions");
    let mut builder = fs::DirBuilder::new();
    #[cfg(unix)]
    {
        use std::os::unix::fs::DirBuilderExt;
        builder.mode(0o700);
    }
    match builder.create(&parent) {
        Ok(()) => (),
        Err(e) if e.kind() == std::io::ErrorKind::AlreadyExists => (),
        Err(_) => {
            return Err(error(
                "RECOVERY_CREATE_FAILED",
                "无法创建独立恢复工作区；原工作库保持不变。",
            ))
        }
    }
    let parent = ordinary_directory(&parent)?;
    let mut random = [0_u8; 16];
    File::open("/dev/urandom")
        .and_then(|mut f| f.read_exact(&mut random))
        .map_err(|_| error("RECOVERY_CREATE_FAILED", "无法生成独立恢复编号。"))?;
    let id: String = random.iter().map(|b| format!("{b:02x}")).collect();
    let directory = parent.join(id);
    builder.create(&directory).map_err(|_| {
        error(
            "RECOVERY_CREATE_FAILED",
            "恢复工作区创建失败，未覆盖已有目录。",
        )
    })?;
    let identity = json!({"schema_version":"ailab-recovery-session-v1", "original_data_dir":original, "recovery_data_dir":directory});
    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(directory.join("recovery-session.json"))
        .map_err(|_| {
            error(
                "RECOVERY_CREATE_FAILED",
                "恢复工作区身份无法保存；已保留目录。",
            )
        })?;
    file.write_all(identity.to_string().as_bytes())
        .and_then(|_| file.sync_all())
        .map_err(|_| {
            error(
                "RECOVERY_CREATE_FAILED",
                "恢复工作区身份无法保存；已保留目录。",
            )
        })?;
    Ok(directory)
}

// 调用方必须先占用 switching 门禁。原库、原 selector 和失败回执都不改写。
pub(super) fn begin(state: &HostState) -> Result<Value, Value> {
    let mut launch = state
        .launch
        .lock()
        .map_err(|_| error("HOST_STATE_ERROR", "无法读取工作库设置。"))?;
    let mut process = state
        .process
        .lock()
        .map_err(|_| error("HOST_STATE_ERROR", "无法读取本地服务状态。"))?;
    if !state.recovery_mode.load(Ordering::SeqCst) {
        if process.status().state == "running" {
            return Err(error(
                "CONTROL_ALREADY_RUNNING",
                "当前工作库已连接，请使用备份与恢复入口。",
            ));
        }
        ordinary_directory(
            state
                .selection_file
                .parent()
                .ok_or_else(|| error("RECOVERY_IDENTITY_INVALID", "工作库选择路径无效。"))?,
        )?;
        let selector = snapshot_file(&state.selection_file)?;
        let directory = create_workspace(&state.fallback.data_dir, &launch.data_dir)?;
        let session = Session::capture(launch.clone(), directory.clone(), selector)?;
        let mut original = state
            .recovery_original
            .lock()
            .map_err(|_| error("HOST_STATE_ERROR", "无法保存原工作库身份。"))?;
        *original = Some(session);
        launch.data_dir = directory;
        configure_launch_fixture(&mut launch, None);
        state.recovery_mode.store(true, Ordering::SeqCst);
    }
    verify_workspace(state)?;
    let status = if process.status().state == "running" {
        process.status()
    } else {
        process
            .start(&launch)
            .map_err(|message| error("RECOVERY_START_FAILED", &message))?
    };
    Ok(described_status(status, &launch, true))
}

fn allows(request: &ApiRequest, host_only: bool) -> bool {
    let path = request.path.split('?').next().unwrap_or("");
    let parts: Vec<_> = path.split('/').collect();
    match (request.method.as_str(), parts.as_slice()) {
        ("GET", ["", "api", "v1", "backups" | "restores"]) => true,
        ("GET", ["", "api", "v1", "restores", id]) => valid_restore_id(id),
        (
            "POST",
            ["", "api", "v1", "restore-plans" | "restores" | "import-grants" | "export-grants"],
        ) => true,
        ("POST" | "DELETE", ["", "api", "v1", "restores", id, "activation"]) => {
            host_only && valid_restore_id(id)
        }
        ("POST" | "DELETE", ["", "api", "v1", "host", "reconfiguration"]) => host_only,
        _ => false,
    }
}

fn valid_restore_id(id: &str) -> bool {
    id.strip_prefix("restore-").is_some_and(|v| {
        v.len() == 32
            && v.bytes()
                .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
    })
}

pub(super) fn target(state: &HostState, path: &Path) -> Result<(), Value> {
    if !state.recovery_mode.load(Ordering::SeqCst) {
        return Ok(());
    }
    let path = ordinary_directory(path)?;
    let original = state
        .recovery_original
        .lock()
        .map_err(|_| error("HOST_STATE_ERROR", "无法核实原工作库。"))?;
    let original = original
        .as_ref()
        .ok_or_else(|| error("HOST_STATE_ERROR", "原工作库身份缺失。"))?;
    // 当前服务只认识 scratch；宿主补上原故障库与应用资料目录的保护边界。
    if path.starts_with(&original.original.data_dir) || path.starts_with(&state.fallback.data_dir) {
        return Err(error(
            "RECOVERY_TARGET_INVALID",
            "请选择原工作库及应用资料目录以外的恢复位置。",
        ));
    }
    Ok(())
}

pub(super) fn request(
    state: &HostState,
    request: &ApiRequest,
    host_only: bool,
) -> Result<(), Value> {
    if !state.recovery_mode.load(Ordering::SeqCst) {
        return Ok(());
    }
    if !allows(request, host_only) {
        return Err(error(
            "RECOVERY_ONLY",
            "恢复工作区只接受备份检查、恢复及明确切换。",
        ));
    }
    let path = request.path.split('?').next().unwrap_or("");
    if request.method == "POST" && matches!(path, "/api/v1/restore-plans" | "/api/v1/export-grants")
    {
        let key = if path.ends_with("restore-plans") {
            "target_dir"
        } else {
            "path"
        };
        let destination = request
            .body
            .as_ref()
            .and_then(|v| v.get(key))
            .and_then(Value::as_str)
            .ok_or_else(|| error("RECOVERY_TARGET_INVALID", "请选择独立恢复目录。"))?;
        target(state, Path::new(destination))?;
    }
    Ok(())
}

pub(super) fn previous_library(
    state: &HostState,
    current: &LaunchConfig,
) -> Result<PathBuf, Value> {
    if !state.recovery_mode.load(Ordering::SeqCst) {
        return Ok(current.data_dir.clone());
    }
    state
        .recovery_original
        .lock()
        .map_err(|_| error("HOST_STATE_ERROR", "无法读取原工作库身份。"))?
        .as_ref()
        .map(|v| v.original.data_dir.clone())
        .ok_or_else(|| error("HOST_STATE_ERROR", "原工作库身份缺失，未保存切换。"))
}

pub(super) fn complete(state: &HostState) -> Result<(), Value> {
    *state
        .recovery_original
        .lock()
        .map_err(|_| error("HOST_STATE_ERROR", "无法更新恢复状态。"))? = None;
    state.recovery_mode.store(false, Ordering::SeqCst);
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn recovery_rejects_execution_and_host_reconfiguration() {
        for (method, path) in [
            ("POST", "/api/v1/attempts"),
            ("POST", "/api/v1/projects"),
            ("POST", "/api/v1/backups"),
            ("GET", "/api/v1/settings"),
            ("PATCH", "/api/v1/ui-context"),
            ("POST", "/api/v1/model-downloads"),
            ("GET", "/api/v1/artifacts/artifact-a/content"),
        ] {
            assert!(
                !allows(
                    &ApiRequest {
                        method: method.into(),
                        path: path.into(),
                        body: None,
                        idempotency_key: None
                    },
                    true
                ),
                "{method} {path}"
            );
        }
        for (method, path) in [
            ("GET", "/api/v1/restores?cursor=abc"),
            ("POST", "/api/v1/restore-plans"),
            ("POST", "/api/v1/restores"),
            ("GET", "/api/v1/backups"),
        ] {
            assert!(allows(
                &ApiRequest {
                    method: method.into(),
                    path: path.into(),
                    body: None,
                    idempotency_key: None
                },
                false
            ));
        }
        let r = ApiRequest {
            method: "POST".into(),
            path: format!("/api/v1/restores/restore-{}/activation", "a".repeat(32)),
            body: None,
            idempotency_key: None,
        };
        assert!(!allows(&r, false));
        assert!(allows(&r, true));
        for method in ["POST", "DELETE"] {
            let r = ApiRequest {
                method: method.into(),
                path: "/api/v1/host/reconfiguration".into(),
                body: Some(json!({})),
                idempotency_key: None,
            };
            assert!(!allows(&r, false));
            assert!(allows(&r, true));
        }
        for path in [
            "/api/v1/host/reconfiguration/",
            "/api/v1/host/reconfiguration/extra",
            "/api/v1/host/other",
        ] {
            let r = ApiRequest {
                method: "POST".into(),
                path: path.into(),
                body: Some(json!({})),
                idempotency_key: None,
            };
            assert!(!allows(&r, true));
        }
    }
    #[test]
    fn recovery_workspace_is_unique_and_preserves_failed_database() {
        let dir = tempfile::tempdir().unwrap();
        let root = dir.path().canonicalize().unwrap();
        fs::write(root.join("control.sqlite3"), b"failed database evidence").unwrap();
        let a = create_workspace(&root, &root).unwrap();
        let b = create_workspace(&root, &root).unwrap();
        assert_ne!(a, b);
        assert_eq!(
            fs::read(root.join("control.sqlite3")).unwrap(),
            b"failed database evidence"
        );
        let identity: Value =
            serde_json::from_slice(&fs::read(a.join("recovery-session.json")).unwrap()).unwrap();
        assert_eq!(
            identity["original_data_dir"],
            root.to_string_lossy().as_ref()
        );
        assert!(!a.join("control.sqlite3").exists());
    }
    #[cfg(unix)]
    #[test]
    fn recovery_workspace_rejects_linked_parent() {
        let dir = tempfile::tempdir().unwrap();
        let root = dir.path().canonicalize().unwrap();
        fs::create_dir(root.join("outside")).unwrap();
        std::os::unix::fs::symlink(root.join("outside"), root.join("recovery-sessions")).unwrap();
        assert!(create_workspace(&root, &root).is_err());
        assert_eq!(fs::read_dir(root.join("outside")).unwrap().count(), 0);
    }

    fn session_fixture(selector_present: bool) -> (tempfile::TempDir, Session, PathBuf) {
        let temporary = tempfile::tempdir().unwrap();
        let profile = temporary.path().canonicalize().unwrap();
        let selector = profile.join("selected-library.json");
        if selector_present {
            fs::write(&selector, b"original selection").unwrap();
        }
        let original = LaunchConfig {
            executable: PathBuf::from("/not-executed"),
            args: vec![],
            cwd: None,
            data_dir: profile.join("failed-library"),
        };
        let workspace = create_workspace(&profile, &original.data_dir).unwrap();
        let session =
            Session::capture(original, workspace, snapshot_file(&selector).unwrap()).unwrap();
        (temporary, session, selector)
    }

    #[test]
    fn session_accepts_normal_workspace_writes_and_unchanged_selector() {
        let (_temporary, session, selector) = session_fixture(true);
        fs::create_dir(session.workspace.join("logs")).unwrap();
        fs::write(
            session.workspace.join("logs/test.log"),
            b"normal scratch activity",
        )
        .unwrap();
        session.verify_workspace().unwrap();
        session.verify_selection(&selector).unwrap();
    }

    #[test]
    fn session_rejects_ordinary_workspace_replacement_even_with_copied_receipt() {
        let (_temporary, session, _) = session_fixture(false);
        let old = session.workspace.with_extension("preserved");
        fs::rename(&session.workspace, &old).unwrap();
        fs::create_dir(&session.workspace).unwrap();
        fs::write(
            session.workspace.join("recovery-session.json"),
            &session.receipt.bytes,
        )
        .unwrap();
        assert!(session.verify_workspace().is_err());
        assert!(old.join("recovery-session.json").is_file());
    }

    #[cfg(unix)]
    #[test]
    fn session_rejects_workspace_link_to_original_directory() {
        let (_temporary, session, _) = session_fixture(false);
        fs::create_dir(&session.original.data_dir).unwrap();
        fs::write(
            session.original.data_dir.join("sentinel"),
            b"preserve original",
        )
        .unwrap();
        fs::rename(
            &session.workspace,
            session.workspace.with_extension("preserved"),
        )
        .unwrap();
        std::os::unix::fs::symlink(&session.original.data_dir, &session.workspace).unwrap();
        assert!(session.verify_workspace().is_err());
        assert_eq!(
            fs::read(session.original.data_dir.join("sentinel")).unwrap(),
            b"preserve original"
        );
        assert!(!session
            .original
            .data_dir
            .join("recovery-session.json")
            .exists());
    }

    #[test]
    fn session_rejects_missing_changed_and_replaced_receipt() {
        for change in ["missing", "changed", "replaced"] {
            let (_temporary, session, _) = session_fixture(false);
            let receipt = session.workspace.join("recovery-session.json");
            if change == "changed" {
                fs::write(&receipt, b"changed receipt").unwrap();
            } else {
                fs::rename(&receipt, receipt.with_extension("preserved")).unwrap();
                if change == "replaced" {
                    fs::write(&receipt, &session.receipt.bytes).unwrap();
                }
            }
            assert!(session.verify_workspace().is_err(), "{change}");
        }
    }

    #[test]
    fn session_selection_preserves_absence_and_rejects_new_file() {
        let (_temporary, session, selector) = session_fixture(false);
        session.verify_selection(&selector).unwrap();
        fs::write(&selector, b"external selection").unwrap();
        assert!(session.verify_selection(&selector).is_err());
        assert_eq!(fs::read(&selector).unwrap(), b"external selection");
    }

    #[test]
    fn session_selection_rejects_changed_deleted_and_replaced_file() {
        for change in ["changed", "deleted", "replaced"] {
            let (_temporary, session, selector) = session_fixture(true);
            if change == "changed" {
                fs::write(&selector, b"external selection").unwrap();
            } else {
                fs::rename(&selector, selector.with_extension("preserved")).unwrap();
                if change == "replaced" {
                    fs::write(&selector, b"original selection").unwrap();
                }
            }
            assert!(session.verify_selection(&selector).is_err(), "{change}");
        }
    }

    #[cfg(unix)]
    #[test]
    fn session_selection_rejects_metadata_change_and_symlink() {
        use std::os::unix::fs::PermissionsExt;
        let (_temporary, session, selector) = session_fixture(true);
        let old_mode = fs::metadata(&selector).unwrap().permissions().mode();
        fs::set_permissions(&selector, fs::Permissions::from_mode(old_mode ^ 0o100)).unwrap();
        assert!(session.verify_selection(&selector).is_err());
        let original = selector.with_extension("preserved");
        fs::rename(&selector, &original).unwrap();
        std::os::unix::fs::symlink(&original, &selector).unwrap();
        assert!(session.verify_selection(&selector).is_err());
        assert_eq!(fs::read(&original).unwrap(), b"original selection");
    }

    #[test]
    fn identity_snapshot_rejects_directory_and_oversized_file() {
        let temporary = tempfile::tempdir().unwrap();
        let directory = temporary.path().canonicalize().unwrap();
        assert!(snapshot_file(&directory).is_err());
        let file = directory.join("oversized");
        fs::write(&file, vec![b'x'; 64 * 1024 + 1]).unwrap();
        assert!(snapshot_file(&file).is_err());
    }
}
