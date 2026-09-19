//! 远端连接凭据仅保存在本产品的本机钥匙串，网页只能得到公开目标信息。

use super::{error, proxy, proxy_host, ApiRequest, HostState};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::{fs::File, io::Read, sync::atomic::Ordering};
use tauri::State;

const SERVICE: &str = "org.gcsa.ailab.remote.credentials.v1";

fn fixed_id(value: &str, prefix: &str) -> bool {
    value.strip_prefix(prefix).is_some_and(|suffix| {
        suffix.len() == 32
            && suffix
                .bytes()
                .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
    })
}

pub(crate) fn valid_target(value: &str) -> bool {
    fixed_id(value, "execution-target-")
}

fn valid_secret(value: &str) -> Result<(), Value> {
    if !(32..=512).contains(&value.len()) || !value.bytes().all(|c| (33..=126).contains(&c)) {
        return Err(error(
            "INVALID_CREDENTIAL",
            "连接凭据须为 32 至 512 位可见英文字符。",
        ));
    }
    Ok(())
}

fn random_reference(prefix: &str) -> Result<String, Value> {
    let mut bytes = [0_u8; 16];
    File::open("/dev/urandom")
        .and_then(|mut file| file.read_exact(&mut bytes))
        .map_err(|_| error("CREDENTIAL_ID_FAILED", "无法生成安全的凭据编号。"))?;
    Ok(format!(
        "{prefix}{}",
        bytes
            .iter()
            .map(|byte| format!("{byte:02x}"))
            .collect::<String>()
    ))
}

fn creation_reference(key: &str) -> Result<String, Value> {
    if key.len() != 36
        || ![8, 13, 18, 23]
            .iter()
            .all(|index| key.as_bytes()[*index] == b'-')
    {
        return Err(error(
            "INVALID_IDEMPOTENCY_KEY",
            "连接登记编号无效，请重新打开登记表单。",
        ));
    }
    let compact = key.replace('-', "");
    let reference = format!("remote-credential-{compact}");
    if !fixed_id(&reference, "remote-credential-") {
        return Err(error(
            "INVALID_IDEMPOTENCY_KEY",
            "连接登记编号无效，请重新打开登记表单。",
        ));
    }
    Ok(reference)
}

#[derive(Clone, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct Binding {
    target_id: String,
    origin: String,
    executor_id: String,
}

impl Binding {
    fn from_target(value: &Value) -> Result<Self, Value> {
        let string = |field| {
            value
                .get(field)
                .and_then(Value::as_str)
                .map(str::to_owned)
                .ok_or_else(|| error("EXECUTION_TARGET_INVALID", "本地服务返回的执行目标无效。"))
        };
        let result = Self {
            target_id: string("id")?,
            origin: string("origin")?,
            executor_id: string("executor_id")?,
        };
        if !valid_target(&result.target_id)
            || result.origin.len() > 2048
            || result.executor_id.len() > 100
        {
            return Err(error(
                "EXECUTION_TARGET_INVALID",
                "本地服务返回的执行目标无效。",
            ));
        }
        Ok(result)
    }
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct StoredCredential {
    schema_version: u32,
    binding: Binding,
    secret: String,
}

fn decode(bytes: &[u8], binding: &Binding) -> Result<String, Value> {
    if bytes.len() > 8192 {
        return Err(error(
            "CREDENTIAL_INVALID",
            "系统凭据格式无效，请重新输入。",
        ));
    }
    let stored: StoredCredential = serde_json::from_slice(bytes)
        .map_err(|_| error("CREDENTIAL_INVALID", "系统凭据格式无效，请重新输入。"))?;
    if stored.schema_version != 1 || &stored.binding != binding {
        return Err(error(
            "CREDENTIAL_BINDING_MISMATCH",
            "凭据与执行目标的地址或身份不一致，请重新输入。",
        ));
    }
    valid_secret(&stored.secret)?;
    Ok(stored.secret)
}

#[cfg(target_os = "macos")]
fn options(reference: &str) -> Result<security_framework::passwords::PasswordOptions, Value> {
    if !fixed_id(reference, "remote-credential-") {
        return Err(error(
            "INVALID_CREDENTIAL_REFERENCE",
            "系统凭据引用格式无效。",
        ));
    }
    let mut options =
        security_framework::passwords::PasswordOptions::new_generic_password(SERVICE, reference);
    options.set_access_synchronized(Some(false));
    Ok(options)
}

#[cfg(target_os = "macos")]
fn save(reference: &str, binding: &Binding, secret: &str) -> Result<(), Value> {
    valid_secret(secret)?;
    match security_framework::passwords::generic_password(options(reference)?) {
        Ok(bytes) => {
            decode(&bytes, binding)?;
        }
        Err(failure) if failure.code() == -25300 => {}
        Err(_) => {
            return Err(error(
                "CREDENTIAL_SAVE_FAILED",
                "无法检查本机钥匙串，请解锁后重试。",
            ))
        }
    }
    let bytes = serde_json::to_vec(&StoredCredential {
        schema_version: 1,
        binding: binding.clone(),
        secret: secret.into(),
    })
    .map_err(|_| error("CREDENTIAL_SAVE_FAILED", "无法准备系统凭据。"))?;
    security_framework::passwords::set_generic_password_options(&bytes, options(reference)?)
        .map_err(|_| {
            error(
                "CREDENTIAL_SAVE_FAILED",
                "无法写入本机钥匙串，请解锁钥匙串后重试。",
            )
        })
}

#[cfg(target_os = "macos")]
fn read(reference: &str, binding: &Binding) -> Result<String, Value> {
    let bytes =
        security_framework::passwords::generic_password(options(reference)?).map_err(|_| {
            error(
                "CREDENTIAL_REQUIRED",
                "本机钥匙串中没有可用凭据，或钥匙串未解锁，请重新输入。",
            )
        })?;
    decode(&bytes, binding)
}

#[cfg(target_os = "macos")]
fn remove(reference: &str, binding: &Binding) -> Result<(), Value> {
    use security_framework::passwords::{delete_generic_password_options, generic_password};
    let bytes = match generic_password(options(reference)?) {
        Ok(bytes) => bytes,
        Err(failure) if failure.code() == -25300 => return Ok(()),
        Err(_) => {
            return Err(error(
                "CREDENTIAL_DELETE_FAILED",
                "目标已断开，但钥匙串条目尚未移除，请解锁后重试。",
            ))
        }
    };
    decode(&bytes, binding)?;
    delete_generic_password_options(options(reference)?).map_err(|_| {
        error(
            "CREDENTIAL_DELETE_FAILED",
            "目标已断开，但钥匙串条目尚未移除，请解锁后重试。",
        )
    })
}

#[cfg(not(target_os = "macos"))]
fn save(_: &str, _: &Binding, _: &str) -> Result<(), Value> {
    Err(error(
        "KEYCHAIN_UNAVAILABLE",
        "此构建尚未接入当前系统的凭据存储。",
    ))
}
#[cfg(not(target_os = "macos"))]
fn read(_: &str, _: &Binding) -> Result<String, Value> {
    Err(error(
        "KEYCHAIN_UNAVAILABLE",
        "此构建尚未接入当前系统的凭据存储。",
    ))
}
#[cfg(not(target_os = "macos"))]
fn remove(_: &str, _: &Binding) -> Result<(), Value> {
    Err(error(
        "KEYCHAIN_UNAVAILABLE",
        "此构建尚未接入当前系统的凭据存储。",
    ))
}

async fn store_async(reference: String, binding: Binding, secret: String) -> Result<(), Value> {
    tauri::async_runtime::spawn_blocking(move || save(&reference, &binding, &secret))
        .await
        .map_err(|_| error("CREDENTIAL_SAVE_FAILED", "写入钥匙串失败。"))?
}
async fn read_async(reference: String, binding: Binding) -> Result<String, Value> {
    tauri::async_runtime::spawn_blocking(move || read(&reference, &binding))
        .await
        .map_err(|_| error("CREDENTIAL_REQUIRED", "读取钥匙串失败，请重新输入。"))?
}
async fn remove_async(reference: String, binding: Binding) -> Result<(), Value> {
    tauri::async_runtime::spawn_blocking(move || remove(&reference, &binding))
        .await
        .map_err(|_| error("CREDENTIAL_DELETE_FAILED", "移除钥匙串凭据失败。"))?
}

struct Gate<'a>(&'a HostState);
impl<'a> Gate<'a> {
    fn enter(state: &'a HostState) -> Result<Self, Value> {
        if state.credential_busy.swap(true, Ordering::SeqCst) {
            return Err(error(
                "CREDENTIAL_OPERATION_PENDING",
                "正在更新连接凭据，请稍候。",
            ));
        }
        let guard = Self(state);
        if state.switching.load(Ordering::SeqCst) {
            return Err(error("LIBRARY_SWITCH_PENDING", "正在切换工作库，请稍候。"));
        }
        super::recovery::require_normal(state)?;
        Ok(guard)
    }
}
impl Drop for Gate<'_> {
    fn drop(&mut self) {
        self.0.credential_busy.store(false, Ordering::SeqCst);
    }
}

fn public_target(mut value: Value) -> Result<Value, Value> {
    Binding::from_target(&value)?;
    let fields = [
        "id",
        "project_id",
        "name",
        "origin",
        "executor_id",
        "revision",
        "created_at",
        "updated_at",
        "credential_ref",
        "credential_status",
        "credential_storage",
        "credential_cleanup_refs",
        "credential_cleanup_required",
        "validation_scope",
        "transport",
        "connection_state",
        "protocol_ready",
        "network_remote_ready",
        "nvidia_ready",
        "nvidia_environment",
        "checked_at",
        "adapters",
        "last_error",
    ];
    value
        .as_object_mut()
        .unwrap()
        .retain(|key, _| fields.contains(&key.as_str()));
    Ok(value)
}

async fn target(state: &HostState, id: &str, revision: u64) -> Result<Value, Value> {
    if !valid_target(id) || revision == 0 {
        return Err(error(
            "EXECUTION_TARGET_INVALID",
            "执行目标编号或版本无效。",
        ));
    }
    let value = proxy(
        state,
        ApiRequest {
            method: "GET".into(),
            path: format!("/api/v1/execution-targets/{id}"),
            body: None,
            idempotency_key: None,
        },
    )
    .await?;
    let value = public_target(value)?;
    if value["id"].as_str() != Some(id) || value["revision"].as_u64() != Some(revision) {
        return Err(error(
            "REVISION_CONFLICT",
            "执行目标已更新，请刷新后再连接。",
        ));
    }
    Ok(value)
}

async fn credential_request(
    state: &HostState,
    id: &str,
    body: Value,
    forget: bool,
) -> Result<Value, Value> {
    credential_operation(state, id, body, if forget { "DELETE" } else { "POST" }, "").await
}

async fn credential_operation(
    state: &HostState,
    id: &str,
    body: Value,
    method: &str,
    suffix: &str,
) -> Result<Value, Value> {
    let key = random_reference("host-credential-")?;
    // 超时后只用同一编号重试，控制层可以返回已生效的结果。
    let mut last = Err(error(
        "CONTROL_UNAVAILABLE",
        "凭据操作结果尚未确认，请刷新目标。",
    ));
    for _ in 0..2 {
        last = proxy_host(
            state,
            ApiRequest {
                method: method.into(),
                path: format!("/api/v1/host/execution-targets/{id}/credentials{suffix}"),
                body: Some(body.clone()),
                idempotency_key: Some(key.clone()),
            },
        )
        .await;
        if !matches!(&last, Err(value) if value["error"]["code"] == "CONTROL_UNAVAILABLE") {
            break;
        }
    }
    last.and_then(public_target)
}

async fn cleanup_pending(state: &HostState, mut target: Value) -> Result<Value, Value> {
    let binding = Binding::from_target(&target)?;
    let pending = target
        .get("credential_cleanup_refs")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    if pending.len() > 16
        || pending.iter().any(|item| {
            item.as_str().is_none_or(|reference| {
                !fixed_id(reference, "remote-credential-")
                    || target["credential_ref"].as_str() == Some(reference)
            })
        })
    {
        return Err(error(
            "CREDENTIAL_CLEANUP_MISMATCH",
            "待清理的系统凭据记录无效。",
        ));
    }
    for reference in pending {
        let removed = remove_async(reference.as_str().unwrap().into(), binding.clone()).await;
        let result =
            match removed {
                Ok(()) => credential_operation(
                    state,
                    &binding.target_id,
                    json!({"credential_ref": reference, "expected_revision": target["revision"]}),
                    "POST",
                    "/cleanup",
                )
                .await,
                Err(failure) => Err(failure),
            };
        match result {
            Ok(updated) => target = updated,
            Err(mut failure) => {
                let detached = target["credential_ref"].is_null();
                failure["error"]["message"] = json!(if detached {
                    "目标已断开；旧钥匙串条目尚未完成清理，请解锁钥匙串后再次清除凭据。"
                } else {
                    "连接凭据已保存；旧钥匙串条目尚未完成清理，请解锁钥匙串后再次验证连接。"
                });
                failure["error"]["details"] =
                    json!({"target": target, "credential_detached": detached});
                return Err(failure);
            }
        }
    }
    Ok(target)
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CreateTargetInput {
    name: String,
    project_id: String,
    origin: String,
    #[serde(default = "default_transport")]
    transport: String,
    executor_id: String,
    credential_token: String,
}

fn default_transport() -> String {
    "loopback_http".into()
}

impl CreateTargetInput {
    fn validate(&self) -> Result<(), Value> {
        if self.name.trim().is_empty()
            || self.name.chars().count() > 120
            || self.project_id.is_empty()
            || self.project_id.len() > 100
            || self.origin.is_empty()
            || self.origin.len() > 2048
            || !matches!(self.transport.as_str(), "loopback_http" | "https")
            || !fixed_id(&self.executor_id, "executor-")
        {
            return Err(error(
                "INVALID_EXECUTION_TARGET",
                "目标名称、项目、地址或执行器编号无效。",
            ));
        }
        valid_secret(&self.credential_token)
    }
}

#[tauri::command]
pub async fn create_execution_target(
    input: CreateTargetInput,
    idempotency_key: String,
    state: State<'_, HostState>,
) -> Result<Value, Value> {
    let _guard = Gate::enter(&state)?;
    input.validate()?;
    let reference = creation_reference(&idempotency_key)?;
    let value = proxy_host(&state, ApiRequest { method: "POST".into(), path: "/api/v1/host/execution-targets".into(),
        body: Some(json!({"name": input.name, "project_id": input.project_id, "origin": input.origin, "transport": input.transport,
            "executor_id": input.executor_id, "credential_token": input.credential_token, "credential_ref": reference})),
        idempotency_key: Some(idempotency_key) }).await?;
    let value = public_target(value)?;
    let binding = Binding::from_target(&value)?;
    if value["credential_ref"].as_str() != Some(&reference) {
        // 旧命令在凭据已经撤销或更换后重放，不重新授权旧口令。
        return Ok(value);
    }
    if let Err(mut failure) = store_async(reference, binding.clone(), input.credential_token).await
    {
        let detached = credential_request(
            &state,
            &binding.target_id,
            json!({"expected_revision": value["revision"]}),
            true,
        )
        .await;
        failure["error"]["details"] = match detached {
            Ok(target) => match cleanup_pending(&state, target.clone()).await {
                Ok(cleaned) => json!({"target": cleaned, "credential_detached": true}),
                Err(cleanup) => {
                    json!({"target": cleanup["error"]["details"]["target"].as_object().map(|_| &cleanup["error"]["details"]["target"]).unwrap_or(&target),
                    "credential_detached": true, "cleanup_error": cleanup["error"]})
                }
            },
            Err(detach_error) => {
                json!({"target": value, "credential_detached": false, "detach_error": detach_error["error"]})
            }
        };
        return Err(failure);
    }
    Ok(value)
}

#[tauri::command]
pub async fn connect_remote_target(
    target_id: String,
    secret: Option<String>,
    expected_revision: u64,
    state: State<'_, HostState>,
) -> Result<Value, Value> {
    let _guard = Gate::enter(&state)?;
    let value =
        cleanup_pending(&state, target(&state, &target_id, expected_revision).await?).await?;
    let binding = Binding::from_target(&value)?;
    let old_reference = value["credential_ref"].as_str().map(str::to_owned);
    let replacing = secret.is_some();
    let (secret, reference) = if let Some(secret) = secret {
        valid_secret(&secret)?;
        let reference = random_reference("remote-credential-")?;
        store_async(reference.clone(), binding.clone(), secret.clone()).await?;
        (secret, reference)
    } else {
        let reference = old_reference
            .clone()
            .ok_or_else(|| error("CREDENTIAL_REQUIRED", "请先输入此执行目标的连接凭据。"))?;
        (
            read_async(reference.clone(), binding.clone()).await?,
            reference,
        )
    };
    let updated = credential_request(&state, &target_id, json!({"credential_token": secret, "credential_ref": reference, "expected_revision": value["revision"]}), false).await;
    let updated = match updated {
        Ok(updated) => updated,
        Err(mut failure) => {
            // 仅确定服务没有采用新引用时清理；未知结果保留钥匙串，供刷新后恢复。
            if replacing {
                if let Ok(current) = proxy(
                    &state,
                    ApiRequest {
                        method: "GET".into(),
                        path: format!("/api/v1/execution-targets/{target_id}"),
                        body: None,
                        idempotency_key: None,
                    },
                )
                .await
                {
                    if current["credential_ref"].as_str() != Some(&reference) {
                        if let Err(cleanup) = remove_async(reference.clone(), binding).await {
                            failure["error"]["details"]["credential_cleanup_error"] =
                                cleanup["error"].clone();
                            failure["error"]["details"]["credential_cleanup_ref"] =
                                json!(reference);
                        }
                    }
                }
            }
            return Err(failure);
        }
    };
    cleanup_pending(&state, updated).await?;
    public_target(
        proxy(
            &state,
            ApiRequest {
                method: "POST".into(),
                path: format!("/api/v1/execution-targets/{target_id}/check"),
                body: Some(json!({})),
                idempotency_key: None,
            },
        )
        .await?,
    )
}

#[tauri::command]
pub async fn forget_remote_target(
    target_id: String,
    expected_revision: u64,
    state: State<'_, HostState>,
) -> Result<Value, Value> {
    let _guard = Gate::enter(&state)?;
    let value = target(&state, &target_id, expected_revision).await?;
    let detached = credential_request(
        &state,
        &target_id,
        json!({"expected_revision": value["revision"]}),
        true,
    )
    .await?;
    cleanup_pending(&state, detached).await
}

#[cfg(test)]
mod tests {
    use super::*;
    fn binding() -> Binding {
        Binding {
            target_id: format!("execution-target-{}", "a".repeat(32)),
            origin: "http://127.0.0.1:12345".into(),
            executor_id: "executor-test".into(),
        }
    }

    #[test]
    fn 凭据绑定地址身份与目标且错误不回传秘密() {
        let original = binding();
        let bytes = serde_json::to_vec(&StoredCredential {
            schema_version: 1,
            binding: original.clone(),
            secret: "x".repeat(40),
        })
        .unwrap();
        assert_eq!(decode(&bytes, &original).unwrap(), "x".repeat(40));
        for field in ["target_id", "origin", "executor_id"] {
            let mut other = original.clone();
            match field {
                "target_id" => other.target_id.push('b'),
                "origin" => other.origin.push('0'),
                _ => other.executor_id.push('b'),
            }
            let failure = decode(&bytes, &other).unwrap_err();
            assert_eq!(failure["error"]["code"], "CREDENTIAL_BINDING_MISMATCH");
            assert!(!failure.to_string().contains(&"x".repeat(40)));
        }
    }

    #[test]
    fn 限制引用目标与可见字符() {
        assert!(valid_target(&binding().target_id));
        for value in [
            "../target",
            "execution-target-xxx",
            "execution-target-0000000000000000000000000000000A",
        ] {
            assert!(!valid_target(value));
        }
        for value in [
            "x".repeat(31),
            "x".repeat(513),
            " ".repeat(32),
            "中".repeat(32),
        ] {
            assert!(valid_secret(&value).is_err());
        }
        assert!(valid_secret(&"x".repeat(32)).is_ok());
        let reference = random_reference("remote-credential-").unwrap();
        assert!(fixed_id(&reference, "remote-credential-"));
        assert_eq!(
            creation_reference("01234567-89ab-cdef-0123-456789abcdef").unwrap(),
            "remote-credential-0123456789abcdef0123456789abcdef"
        );
        for key in [
            "x",
            "0123456789abcdef0123456789abcdef----",
            "01234567-89ab-cdef-0123-456789abcdeG",
        ] {
            assert!(creation_reference(key).is_err());
        }
    }

    #[test]
    fn 公开目标不含令牌或任意身份响应() {
        let value = json!({"id":binding().target_id, "origin":"https://executor.example", "executor_id":"executor-test", "transport":"https", "validation_scope":"https_protocol_only", "credential_token":"secret", "secret":"secret", "identity":{"secret":"secret"}, "revision":1});
        let public = public_target(value).unwrap();
        assert_eq!(public["transport"], "https");
        assert_eq!(public["origin"], "https://executor.example");
        assert!(public.get("secret").is_none());
        assert!(public.get("credential_token").is_none());
        assert!(public.get("identity").is_none());
    }

    #[test]
    fn 传输方式受限且凭据使用控制端规范地址绑定() {
        let payload = json!({"name":"执行服务", "project_id":"project-test", "origin":"https://executor.example", "executor_id":format!("executor-{}", "a".repeat(32)), "credential_token":"x".repeat(40)});
        let legacy: CreateTargetInput = serde_json::from_value(payload.clone()).unwrap();
        assert_eq!(legacy.transport, "loopback_http");
        for mode in ["https", "loopback_http"] {
            let mut value = payload.clone();
            value["transport"] = json!(mode);
            assert!(serde_json::from_value::<CreateTargetInput>(value).unwrap().validate().is_ok());
        }
        let mut invalid = payload;
        invalid["transport"] = json!("insecure_https");
        assert!(serde_json::from_value::<CreateTargetInput>(invalid).unwrap().validate().is_err());

        let canonical = Binding::from_target(&json!({"id":binding().target_id, "origin":"https://executor.example", "executor_id":binding().executor_id})).unwrap();
        let bytes = serde_json::to_vec(&StoredCredential { schema_version:1, binding:canonical.clone(), secret:"x".repeat(40) }).unwrap();
        assert_eq!(decode(&bytes, &canonical).unwrap(), "x".repeat(40));
        let mut raw = canonical.clone();
        raw.origin = "HTTPS://Executor.Example:443/".into();
        assert_eq!(decode(&bytes, &raw).unwrap_err()["error"]["code"], "CREDENTIAL_BINDING_MISMATCH");
    }

    #[cfg(target_os = "macos")]
    #[test]
    #[ignore = "仅显式验收时在本产品命名空间创建独立条目并立即移除"]
    fn 本机钥匙串真实保存读取绑定与清除() {
        let reference = random_reference("remote-credential-").unwrap();
        let binding = binding();
        let secret = random_reference("keychain-acceptance-").unwrap();
        save(&reference, &binding, &secret).unwrap();
        let result = read(&reference, &binding);
        let mut other = binding.clone();
        other.executor_id.push_str("-wrong");
        let mismatch = read(&reference, &other);
        let removed = remove(&reference, &binding);
        assert_eq!(result.unwrap(), secret);
        assert_eq!(
            mismatch.unwrap_err()["error"]["code"],
            "CREDENTIAL_BINDING_MISMATCH"
        );
        removed.unwrap();
        assert!(read(&reference, &binding).is_err());
        remove(&reference, &binding).unwrap();
    }
}
