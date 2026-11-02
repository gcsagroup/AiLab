import { useState, type RefObject } from 'react';
import { errorMessage, pickStudioPath } from '../api';
import { Error, Field } from './common';
import type { Asset } from './types';

export default function GgufModelSelect({ value, items, onChange, selectRef }: { value: string; items: Asset[]; onChange: (path: string) => void; selectRef?: RefObject<HTMLSelectElement | null> }) {
  const [picking, setPicking] = useState(false); const [error, setError] = useState('');
  const options = [...new Map(items.filter(item => item.format === 'gguf').map(item => [item.path, item])).values()];
  if (value && !options.some(item => item.path === value)) options.push({ path:value, name:value.split(/[\\/]/).at(-1) || value, format:'gguf' });
  async function select(path: string) {
    setError('');
    if (path !== '__other__') { onChange(path); return; }
    setPicking(true);
    try {
      const selected = await pickStudioPath(false, true);
      if (selected) {
        if (!selected.toLowerCase().endsWith('.gguf')) throw new globalThis.Error('请选择 .gguf 模型权重文件');
        onChange(selected);
      }
    } catch (e) { setError(errorMessage(e)); }
    finally { setPicking(false); }
  }
  return <div><Field title="本地模型"><select ref={selectRef} value={value} disabled={picking} onChange={e => { void select(e.target.value); }}>
    <option value="">{picking ? '正在选择模型…' : '请选择 GGUF 模型'}</option>
    {options.map(item => <option key={item.path} value={item.path}>{item.name}{item.size_gb ? ` · ${item.size_gb} GB` : ''}</option>)}
    <option value="__other__">选择其他模型…</option>
  </select></Field>{value && <small className="st-model-path" title={value}>{value}</small>}<Error text={error} /></div>;
}
