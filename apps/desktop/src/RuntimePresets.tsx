import { useState } from 'react';
import type { Runtime } from './types';
import { Button, Dialog } from './ui';

const presets = [
  { id: 'default', name: '模型默认', kv: 'auto', block: 2048, description: '保留模型缓存精度，提示词按最多 2048 个词元分块。' },
  { id: 'low_memory_v2', name: '低内存', kv: 'auto', block: 512, description: '保留模型缓存精度，将提示词分块上限改为 512。已测中长输入的生成峰值内存较低，但首字可能更慢；短输入没有稳定收益。KV 缓存精度和最终大小保持不变。' },
  { id: 'low_latency', name: '低延迟', kv: 'auto', block: 4096, description: '保留模型缓存精度，将提示词分块上限改为 4096。已测长输入只有小幅延迟改善，4-bit 权重组合的内存可能更高；实际速度取决于输入和设备。' },
] as const;

type InferenceRuntime = Runtime & { kv_precision?: 'auto' | 'q4'; prefill_step_size?: number };
export function RuntimePresets({ runtime, disabled, onApply }: { runtime: InferenceRuntime; disabled?: boolean; onApply: (runtime: InferenceRuntime) => void }) {
  const [selected, setSelected] = useState('default'); const [open, setOpen] = useState(false);
  const preset = presets.find(item => item.id === selected)!;
  const precision = runtime.kv_precision || 'auto'; const block = runtime.prefill_step_size ?? 2048;
  const current = presets.find(item => item.kv === precision && item.block === block)?.name || '自定义';
  return <div className="form-stack"><label>运行预设<select value={selected} disabled={disabled} onChange={e => setSelected(e.target.value)}>{presets.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><small className="muted">当前配置：{current}。选择后先查看差异，应用只修改草稿。</small><Button data-timing-action="preview_preset" disabled={disabled} onClick={() => setOpen(true)}>预览预设差异</Button>
    {open && <Dialog title={`应用${preset.name}预设`} onClose={() => setOpen(false)}><p className="muted">{preset.description}</p><table className="preset-diff"><thead><tr><th>参数</th><th>当前值</th><th>应用后</th></tr></thead><tbody><tr><th>KV 缓存精度</th><td>{precision === 'q4' ? '4-bit' : '模型精度'}</td><td>模型精度</td></tr><tr><th>提示词分块上限</th><td>{block} 词元</td><td>{preset.block} 词元</td></tr></tbody></table><p className="muted">最大输出仍为 {runtime.max_tokens} 个 token，温度 {runtime.temperature}、Top-p {runtime.top_p}、种子 {runtime.seed}。每次运行新建缓存；没有跨请求前缀复用。</p><p className="warning">应用后需保存并重新检查配置。当前只支持本机固定 Qwen 文本生成组合，效果以真实运行记录为准。</p><div className="dialog-footer"><Button onClick={() => setOpen(false)}>取消</Button><Button primary disabled={disabled} onClick={() => { onApply({ ...runtime, kv_precision: preset.kv, prefill_step_size: preset.block }); setOpen(false); }}>应用到草稿</Button></div></Dialog>}
  </div>;
}
