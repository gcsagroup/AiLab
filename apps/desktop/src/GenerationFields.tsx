import { useEffect, useId, useRef, useState } from 'react';
import type { Runtime } from './types';

export function GenerationFields({ runtime, disabled, onChange }: { runtime: Runtime; disabled?: boolean; onChange: (runtime: Runtime) => void }) {
  const id = useId();
  const stopValue = JSON.stringify(runtime.stop ?? []);
  const synchronizedStop = useRef(stopValue);
  const [stopText, setStopText] = useState(() => (runtime.stop ?? []).join('\n'));
  useEffect(() => {
    if (stopValue !== synchronizedStop.current) {
      synchronizedStop.current = stopValue;
      setStopText((JSON.parse(stopValue) as string[]).join('\n'));
    }
  }, [stopValue]);
  const context = runtime.context_limit ?? 4096;
  const contextError = !Number.isInteger(context) || context < 128 || context > 4096 ? '上下文总预算必须是 128—4096 之间的整数词元；当前值未被自动调整。' : '';
  const stops = runtime.stop ?? [];
  const stopError = stops.length > 8 ? '停止序列最多 8 条；请减少条数后保存。'
    : stops.some(item => Array.from(item).length < 1 || Array.from(item).length > 128) ? '每条停止序列必须是 1—128 个字符；输入未被截断。'
      : new Set(stops).size !== stops.length ? '停止序列不能重复；请修改后保存。'
        : stops.some(item => /[\u0000-\u0008\u000b-\u001f\u007f]/.test(item)) ? '停止序列不能包含控制字符；制表符可以保留。' : '';
  function changeStops(value: string) {
    const stop = value.split(/\r?\n/).filter(line => line !== '');
    setStopText(value);
    // 保存规范化数组，同时保留正在输入的尾部换行；其他字段更新不能吞掉新的一行。
    synchronizedStop.current = JSON.stringify(stop);
    onChange({ ...runtime, stop });
  }
  return <div className="form-stack" aria-label="文本生成设置">
    <div className="two-fields"><label>上下文总预算（词元）<input type="number" min={128} max={4096} step={1} value={context} disabled={disabled} aria-invalid={Boolean(contextError)} aria-describedby={`${id}-context-help${contextError ? ` ${id}-context-error` : ''}`} onChange={event => onChange({ ...runtime, context_limit: Number(event.target.value) })} /></label><label>输入超限处理<select value="reject" disabled aria-describedby={`${id}-context-help`}><option value="reject">拒绝运行，保留完整输入</option></select></label></div>
    <small className="muted" id={`${id}-context-help`}>预算包含聊天模板、输入和完整最大输出预留。当前只有单条输入，超限时明确提示；不会裁剪内容。</small>
    {contextError && <p className="error" role="alert" id={`${id}-context-error`}>{contextError}</p>}
    <label>停止序列<textarea rows={4} value={stopText} disabled={disabled} aria-invalid={Boolean(stopError)} aria-describedby={`${id}-stop-help${stopError ? ` ${id}-stop-error` : ''}`} placeholder="每行一个，例如：完成" onChange={event => changeStops(event.target.value)} /></label>
    <small className="muted" id={`${id}-stop-help`}>每行一个，最多 8 条，每条 1—128 个字符。Enter 新增一行；空行忽略，首尾空格与只含空格的行均按原样匹配。命中后停止生成，结果不含该序列。</small>
    {stopError && <p className="error" role="alert" id={`${id}-stop-error`}>{stopError}</p>}
    <label style={{ display: 'flex', alignItems: 'center' }}><input type="checkbox" style={{ width: 'auto' }} checked={runtime.stream ?? true} disabled={disabled} onChange={event => onChange({ ...runtime, stream: event.target.checked })} />流式显示输出</label>
    <small className="muted">关闭后在本次生成完成时显示结果；运行状态、停止操作和最终结果保存仍然可用。</small>
    <label>思考模式<select value="default" disabled aria-describedby={`${id}-thinking-help`}><option value="default">模型默认</option></select></label>
    <small className="muted" id={`${id}-thinking-help`}>当前 Qwen2.5 模型与模板没有思考开关。</small>
  </div>;
}
