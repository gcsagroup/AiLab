import { useCallback, useEffect, useRef } from 'react';
import { canPickFile, recordFirstFrame } from './api';

export type StartupStage = 'frontend_mounted' | 'host_running_observed' | 'host_disconnected_observed'
  | 'projects_started' | 'projects_ready' | 'resources_started' | 'resources_ready'
  | 'environment_started' | 'capabilities_ready' | 'devices_ready'
  | 'all_conditions_ready' | 'conditions_not_ready' | 'visible' | 'hidden'
  | 'first_animation_frame' | 'second_animation_frame';
export type StartupPhases = { time_origin_unix_ms: number; events: { stage: StartupStage; at_ms: number }[]; omitted_events: number };

/** 数据就绪且窗口可见后等待两帧，只向本机宿主报告第一次首屏。 */
export function useStartupReceipt(ready: boolean, view: 'empty_library' | 'project_home') {
  const reported = useRef(false);
  const phases = useRef<StartupPhases | null>(null);
  if (!phases.current) phases.current = { time_origin_unix_ms: performance.timeOrigin, events: [{ stage: 'frontend_mounted', at_ms: performance.now() }], omitted_events: 0 };
  const mark = useCallback((stage: StartupStage) => {
    if (reported.current) return;
    const detail = phases.current!;
    // 只存固定阶段与本页单调时钟；反复断连不会无限占用内存。
    if (detail.events.length < 64) detail.events.push({ stage, at_ms: performance.now() });
    else detail.omitted_events += 1;
  }, []);
  useEffect(() => {
    if (!canPickFile() || reported.current) return;
    mark(ready ? 'all_conditions_ready' : 'conditions_not_ready');
    if (!ready) return;
    let first = 0, second = 0, disposed = false;
    const visible = () => {
      cancelAnimationFrame(first); cancelAnimationFrame(second);
      mark(document.visibilityState === 'visible' ? 'visible' : 'hidden');
      if (document.visibilityState !== 'visible') return;
      first = requestAnimationFrame(() => {
        mark('first_animation_frame');
        second = requestAnimationFrame(() => {
          if (disposed || reported.current || document.visibilityState !== 'visible') return;
          mark('second_animation_frame');
          reported.current = true;
          // 计时回执缺失由验收报告判为测量不完整，不影响用户继续操作。
          void recordFirstFrame(view, phases.current!).catch(() => {});
        });
      });
    };
    visible(); document.addEventListener('visibilitychange', visible);
    return () => { disposed = true; cancelAnimationFrame(first); cancelAnimationFrame(second); document.removeEventListener('visibilitychange', visible); };
  }, [ready, view, mark]);
  return mark;
}
