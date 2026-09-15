import { useEffect, useRef, useState } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { listen } from '@tauri-apps/api/event';
import { canPickFile, errorMessage } from './api';

/** 原生确认退出后先保存；宿主超时或保存失败时继续保留当前界面。 */
export function useExitPreparation(prepare: () => Promise<void>) {
  const latest = useRef(prepare); latest.current = prepare;
  const [preparing, setPreparing] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    if (!canPickFile()) return;
    let disposed = false; let requestId: number | null = null;
    let unlisten: (() => void) | undefined;
    void listen<{ request_id: number; cancelled: boolean }>('prepare-exit', event => {
      const id = event.payload.request_id;
      if (disposed) return;
      if (event.payload.cancelled) {
        if (requestId === id) { requestId = null; setPreparing(false); setError('退出前保存未完成，应用已保留，请重试。'); }
        return;
      }
      if (requestId !== null) return;
      requestId = id; setPreparing(true); setError('');
      void (async () => {
        let success = false;
        try { await latest.current(); success = true; }
        catch (e) { if (!disposed && requestId === id) setError(`尚未退出：${errorMessage(e)}`); }
        if (disposed || requestId !== id) return;
        try { await invoke('complete_exit_preparation', { requestId: id, success }); }
        catch (e) { if (!disposed && requestId === id) { success = false; setError(`尚未退出：${errorMessage(e)}`); } }
        if (!success && !disposed && requestId === id) { requestId = null; setPreparing(false); }
      })();
    }).then(stop => { if (disposed) stop(); else unlisten = stop; }).catch(e => { if (!disposed) setError(`退出前保存检查未就绪：${errorMessage(e)}`); });
    return () => { disposed = true; requestId = null; unlisten?.(); };
  }, []);
  return { preparing, error };
}
