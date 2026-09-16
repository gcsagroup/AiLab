import type { ModelExecutionBoundary } from './types';

export function hasKnownModelBoundary(boundary?: ModelExecutionBoundary): boolean {
  return boundary?.scope_semantics === 'loader_policy_not_os_permissions'
    && boundary.process === 'separate_process' && boundary.os_sandbox === false
    && boundary.filesystem === 'current_user_permissions'
    && boundary.network === 'offline_loader_options_not_os_block'
    && boundary.credentials === 'environment_allowlist_not_filesystem_denial'
    && boundary.custom_code === 'not_supported';
}

export function ModelExecutionNotice({ loadingLabel }: { loadingLabel?: string }) {
  return <section aria-label="模型加载与权限说明"><h4>{loadingLabel ? '加载信任' : '运行权限'}</h4>{loadingLabel && <p>{loadingLabel}</p>}<p>仅使用固定加载器，不支持模型自定义代码。运行时使用独立进程，仍具有当前用户的文件权限，未启用操作系统沙箱。</p><p className="muted">加载器使用本机文件与离线选项；这不代表系统已阻断网络。工作进程仅继承允许的环境变量，不传入应用凭证；这不代表系统已阻止读取凭证文件。</p></section>;
}
