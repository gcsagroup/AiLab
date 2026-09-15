//! Python 环境选择保留用户选中的链接路径；不能把 venv 解释器换成链接目标。
use serde_json::Value;
use std::path::PathBuf;

#[cfg(not(target_os = "macos"))]
pub fn pick_file(_app: &tauri::AppHandle, title: String) -> Result<Option<PathBuf>, Value> {
    Ok(rfd::FileDialog::new().set_title(title).pick_file())
}

#[cfg(target_os = "macos")]
pub use macos::pick_file;

#[cfg(target_os = "macos")]
mod macos {
    use super::*;
    use crate::error;
    use objc2::{rc::autoreleasepool, MainThreadMarker};
    use objc2_app_kit::{NSModalResponse, NSModalResponseCancel, NSModalResponseOK, NSOpenPanel};
    use objc2_foundation::{NSString, NSURL};
    use std::sync::mpsc;

    pub fn pick_file(app: &tauri::AppHandle, title: String) -> Result<Option<PathBuf>, Value> {
        if MainThreadMarker::new().is_some() {
            return pick_on_main_thread(&title);
        }
        let (sender, receiver) = mpsc::sync_channel(1);
        app.run_on_main_thread(move || {
            // 只跨线程传拥有所有权的路径/错误；AppKit 对象在主线程内创建和释放。
            let _ = sender.send(pick_on_main_thread(&title));
        })
        .map_err(|_| error("FILE_DIALOG_FAILED", "无法安排执行环境选择窗口。"))?;
        receiver
            .recv()
            .map_err(|_| error("FILE_DIALOG_FAILED", "执行环境选择窗口已中断。"))?
    }

    fn pick_on_main_thread(title: &str) -> Result<Option<PathBuf>, Value> {
        let main = MainThreadMarker::new()
            .ok_or_else(|| error("FILE_DIALOG_FAILED", "执行环境选择窗口必须在主线程打开。"))?;
        autoreleasepool(|_| {
            let panel = NSOpenPanel::openPanel(main);
            // NSOpenPanel 默认解析别名；Python venv 的符号链接必须保持所选路径。
            panel.setResolvesAliases(false);
            panel.setCanChooseFiles(true);
            panel.setCanChooseDirectories(false);
            panel.setAllowsMultipleSelection(false);
            panel.setMessage(Some(&NSString::from_str(title)));
            let response = panel.runModal();
            let url = if response == NSModalResponseOK {
                panel.URL()
            } else {
                None
            };
            selected_path(response, url.as_deref())
        })
    }

    fn selected_path(
        response: NSModalResponse,
        url: Option<&NSURL>,
    ) -> Result<Option<PathBuf>, Value> {
        if response == NSModalResponseCancel {
            return Ok(None);
        }
        if response != NSModalResponseOK {
            return Err(error("FILE_DIALOG_FAILED", "执行环境选择窗口未能完成。"));
        }
        let path = url
            .filter(|url| url.isFileURL())
            .and_then(NSURL::to_file_path)
            .filter(|path| path.is_absolute())
            .ok_or_else(|| error("FILE_DIALOG_FAILED", "选择窗口没有返回有效的本地文件路径。"))?;
        // 仅转换面板返回的 NSURL，不规范化路径、不根据解释器目标推断虚拟环境。
        Ok(Some(path))
    }

    #[cfg(test)]
    mod tests {
        use super::*;
        use std::{fs, os::unix::fs::symlink};

        #[test]
        fn foundation_file_url_preserves_real_symlink_and_unicode_path() {
            autoreleasepool(|_| {
                let directory = tempfile::tempdir().unwrap();
                let target = directory.path().join("base-python");
                fs::write(&target, b"never executed").unwrap();
                let environment = directory.path().join("测试 环境 %20/.venv/bin");
                fs::create_dir_all(&environment).unwrap();
                let selected = environment.join("python");
                symlink(&target, &selected).unwrap();
                let url = NSURL::from_file_path(&selected).unwrap();
                // 真实 Foundation 转换和文件链接；没有创建 NSOpenPanel，也不替代原生验收。
                let actual = selected_path(NSModalResponseOK, Some(&url))
                    .unwrap()
                    .unwrap();
                assert_eq!(actual, selected);
                assert_ne!(actual, selected.canonicalize().unwrap());
                assert_eq!(fs::read_link(&actual).unwrap(), target);
            });
        }

        #[test]
        fn foundation_regular_file_url_is_preserved() {
            autoreleasepool(|_| {
                let directory = tempfile::tempdir().unwrap();
                let selected = directory.path().join("python3");
                fs::write(&selected, b"never executed").unwrap();
                let url = NSURL::from_file_path(&selected).unwrap();
                assert_eq!(
                    selected_path(NSModalResponseOK, Some(&url)).unwrap(),
                    Some(selected)
                );
            });
        }

        #[test]
        fn cancellation_and_incomplete_panel_results_are_distinct() {
            assert!(selected_path(NSModalResponseCancel, None)
                .unwrap()
                .is_none());
            for response in [NSModalResponseOK, -1001, 123] {
                assert_eq!(
                    selected_path(response, None).unwrap_err()["error"]["code"],
                    "FILE_DIALOG_FAILED"
                );
            }
        }

        #[test]
        fn non_file_urls_are_not_accepted_as_local_python_paths() {
            autoreleasepool(|_| {
                let url =
                    NSURL::URLWithString(&NSString::from_str("https://example.invalid/python"))
                        .unwrap();
                assert_eq!(
                    selected_path(NSModalResponseOK, Some(&url)).unwrap_err()["error"]["code"],
                    "FILE_DIALOG_FAILED"
                );
                assert!(selected_path(NSModalResponseCancel, Some(&url))
                    .unwrap()
                    .is_none());
            });
        }

        #[test]
        fn worker_thread_is_rejected_before_creating_an_appkit_panel() {
            std::thread::spawn(|| {
                assert!(MainThreadMarker::new().is_none());
                assert_eq!(
                    pick_on_main_thread("不得创建窗口").unwrap_err()["error"]["code"],
                    "FILE_DIALOG_FAILED"
                );
            })
            .join()
            .unwrap();
        }
    }
}
