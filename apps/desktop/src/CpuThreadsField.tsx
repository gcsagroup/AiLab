import type { Device } from './types';

export function CpuThreadsField({ devices, value, onChange }: {
  devices: Device[]; value?: number; onChange: (threads: number) => void;
}) {
  const maximum = devices.find(device => device.id === 'cpu')?.logical_processors;
  return <label>CPU 逻辑核心数<select value={value ?? maximum ?? ''} disabled={!maximum}
    onChange={event => onChange(Number(event.target.value))}>
    {!maximum && <option value={value ?? ''}>{value ?? '全部（自动检测）'}</option>}
    {maximum && value !== undefined && (value > maximum || value < 1 || !Number.isInteger(value)) &&
      <option value={value} disabled>已保存 {value}，请重新选择</option>}
    {Array.from({ length: maximum ?? 0 }, (_, index) => index + 1).map(count =>
      <option key={count} value={count}>{count === maximum ? `${count}（全部）` : count}</option>)}
  </select></label>;
}
