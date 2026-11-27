import { useId, useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { Button } from './ui';

export const outputPreviewLimit = 65536;

const delimiters = [
  { open: '<think>', close: '</think>' },
  { open: '<|channel>thought', close: '<channel|>' },
];

// The view receives the accumulated stream. Only interpret a reasoning
// prefix at the assistant boundary, so examples of these tags in answers survive.
function splitOutput(text: string, active: boolean, prefilled: boolean) {
  const start = text.trimStart();
  const pair = delimiters.find(({ open }) => start.startsWith(open));
  if (!pair && !prefilled) {
    const pending = active && delimiters.some(({ open }) => open.startsWith(start));
    return { answer: pending ? '' : text, thought: '', closed: false, started: false };
  }
  const close = pair?.close ?? '</think>';
  const body = pair ? start.slice(pair.open.length) : text;
  const end = body.indexOf(close);
  if (end >= 0) {
    return { answer: body.slice(end + close.length).replace(/^(?:\r?\n)+/, ''), thought: body.slice(0, end).trim(), closed: true, started: true };
  }
  const tail = body.lastIndexOf('<');
  const visible = tail >= 0 && close.startsWith(body.slice(tail)) ? body.slice(0, tail) : body;
  return { answer: '', thought: visible.trim(), closed: false, started: true };
}

export function TrialTextOutput({ text, reasoning, prefilled = false, active }: {
  text: string; reasoning?: string; prefilled?: boolean; active: boolean;
}) {
  const panelId = useId();
  const [toggle, setToggle] = useState<{ thinking: boolean; expanded: boolean }>();
  const { answer, thought, closed, started } = reasoning === undefined
    ? splitOutput(text, active, prefilled)
    : { answer: text, thought: reasoning.trim(), closed: Boolean(text), started: Boolean(reasoning) };
  const thinking = started && active && !closed;
  const expanded = toggle?.thinking === thinking ? toggle.expanded : thinking;
  const hasThought = Boolean(thought) || thinking;
  return <div className="model-output" aria-label="模型输出">
    {hasThought && <div className="trial-reasoning">
      <Button aria-expanded={expanded} aria-controls={panelId} onClick={() => setToggle({ thinking, expanded: !expanded })}>
        {expanded ? <ChevronDown size={14} aria-hidden="true" /> : <ChevronRight size={14} aria-hidden="true" />}
        {thinking ? '正在思考' : expanded ? '收起思考过程' : '查看思考过程'}
      </Button>
      <div id={panelId} className="trial-reasoning-text" hidden={!expanded}>{thought.slice(0, outputPreviewLimit)}</div>
    </div>}
    {answer && <div>{answer.slice(0, outputPreviewLimit)}</div>}
    {thought && !answer && !active && <small className="muted">本次生成在输出最终回答前结束。</small>}
  </div>;
}
