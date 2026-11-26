import type { Kind, Model } from './types';

export function libraryModelKind(model: Model): Kind {
  return model.modality ?? model.kind ?? 'text';
}

const labels: Record<Kind, string> = {
  text: '语言与多模态理解', image: '图片', video: '视频', audio: '音频',
};

export function TrialModelSelect({ id, models, kind, value, onChange, onImport, ariaLabel }: {
  id: string; models: Model[]; kind: Kind; value: string | null; onChange: (id: string) => void;
  onImport?: () => void; ariaLabel?: string;
}) {
  const options = models.filter(model => libraryModelKind(model) === kind);
  return <div className="field">
    <div className="label-action">
      <label htmlFor={id}>模型库 · {labels[kind]}</label>
      {onImport && <button type="button" onClick={onImport}>导入模型</button>}
    </div>
    <select id={id} aria-label={ariaLabel} value={value || ''} onChange={event => onChange(event.target.value)}>
      <option value="">{options.length ? '选择模型库中的模型' : '当前项目模型库中暂无此类模型'}</option>
      {value && !options.some(model => model.id === value) && <option value={value} disabled>原模型已不在当前列表 · {value}</option>}
      {options.map(model => <option key={model.id} value={model.id} disabled={model.execution_available === false}>
        {model.name}{model.execution_available === false ? ' · 当前不可试用' : ''}
      </option>)}
    </select>
  </div>;
}
