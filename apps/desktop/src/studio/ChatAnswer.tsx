import { useEffect, useRef, useState } from 'react';

export default function ChatAnswer({ text, reasoning = '', streaming = false }: { text: string; reasoning?: string; streaming?: boolean }) {
  const [expanded, setExpanded] = useState(streaming && !text);
  const wasThinking = useRef(streaming && !text);
  useEffect(() => {
    const thinking = streaming && !text;
    if (thinking !== wasThinking.current) setExpanded(thinking);
    wasThinking.current = thinking;
  }, [streaming, text]);
  return <div className="st-chat-answer">{reasoning && <details className="st-thinking" open={expanded} onToggle={e => setExpanded(e.currentTarget.open)}><summary>{streaming && !text ? '正在思考…' : '思考过程'}</summary><div>{reasoning}</div></details>}{text && <div className="st-answer-text">{text}</div>}{streaming && !text && !reasoning && <span className="st-note">等待模型输出…</span>}</div>;
}
