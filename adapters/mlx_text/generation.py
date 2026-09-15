"""固定单条文本组合的上下文、停止序列与展示流；不裁剪用户输入。"""

FIELDS = {'context_limit', 'overflow', 'stop', 'stream', 'thinking'}


class GenerationError(ValueError):
    def __init__(self, code, message, **details):
        super().__init__(message)
        self.code, self.details = code, details


def resolve(runtime):
    context = runtime.get('context_limit', 4096)
    if type(context) is not int or not 128 <= context <= 4096:
        raise GenerationError('UNSUPPORTED_PARAMETER', '上下文总预算必须是 128—4096 之间的整数词元。')
    if runtime.get('overflow', 'reject') != 'reject':
        raise GenerationError('UNSUPPORTED_PARAMETER', '当前只有单条输入，没有可裁剪的旧对话；超限处理只支持 reject。')
    if runtime.get('thinking', 'default') != 'default':
        raise GenerationError('UNSUPPORTED_PARAMETER', '当前 Qwen2.5 模型与模板没有思考开关，只支持模型默认行为。')
    stream = runtime.get('stream', True)
    if type(stream) is not bool:
        raise GenerationError('UNSUPPORTED_PARAMETER', '流式输出必须为 true 或 false。')
    stop = runtime.get('stop', [])
    if type(stop) is not list or len(stop) > 8:
        raise GenerationError('UNSUPPORTED_PARAMETER', '停止序列必须是最多 8 项的字符串数组。')
    for item in stop:
        if type(item) is not str or not 1 <= len(item) <= 128:
            raise GenerationError('UNSUPPORTED_PARAMETER', '每个停止序列必须是 1—128 个字符；空格按原样匹配。')
        try:
            item.encode('utf-8')
        except UnicodeEncodeError as exc:
            raise GenerationError('UNSUPPORTED_PARAMETER', '停止序列必须是有效 Unicode 文本。') from exc
        if any((ord(char) < 32 and char not in '\n\t') or ord(char) == 127 for char in item):
            raise GenerationError('UNSUPPORTED_PARAMETER', '停止序列不能包含控制字符；换行与制表符除外。')
    if len(set(stop)) != len(stop):
        raise GenerationError('UNSUPPORTED_PARAMETER', '停止序列不能重复。')
    return {'context_limit': context, 'overflow': 'reject', 'stop': list(stop), 'stream': stream, 'thinking': 'default'}


def prepare_prompt(tokenizer, inputs, effective):
    tokens = tokenizer.apply_chat_template([{'role': 'user', 'content': inputs['prompt']}], tokenize=True, add_generation_prompt=True)
    report = {'prompt_tokens': len(tokens), 'reserved_output_tokens': effective['max_tokens'],
              'total_token_budget': len(tokens) + effective['max_tokens'], 'context_limit': effective['context_limit'],
              'overflow': effective['overflow'], 'input_truncated': False,
              'budget_scope': '真实聊天模板与输入分词，加上完整最大输出预留；当前无历史或媒体。'}
    if report['total_token_budget'] > effective['context_limit']:
        raise GenerationError('CONTEXT_TOO_LONG', f"实际输入 {len(tokens)} 加最大输出 {effective['max_tokens']}，超过本次 {effective['context_limit']} 词元总预算；输入未裁剪。", check_report=report)
    return tokens, report


class StopBuffer:
    """保留可能跨块的停止前缀；按最早完成位置停止，结果不依赖文本分块。"""
    def __init__(self, sequences):
        self.sequences, self.pending, self.matched_index = tuple(sequences), '', None

    @property
    def stopped(self):
        return self.matched_index is not None

    def feed(self, text):
        if self.stopped:
            raise RuntimeError('停止后不能继续送入模型文本')
        self.pending += text
        matches = [(start + len(stop), start, index) for index, stop in enumerate(self.sequences)
                   if (start := self.pending.find(stop)) >= 0]
        if matches:
            _, start, self.matched_index = min(matches)
            visible, self.pending = self.pending[:start], ''
            return visible
        keep = max((size for stop in self.sequences for size in range(1, min(len(stop), len(self.pending) + 1))
                    if self.pending.endswith(stop[:size])), default=0)
        visible = self.pending[:-keep] if keep else self.pending
        self.pending = self.pending[-keep:] if keep else ''
        return visible

    def finish(self):
        visible, self.pending = self.pending, ''
        return visible
