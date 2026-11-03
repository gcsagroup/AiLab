"""Incremental, delimiter-based reasoning split; never guess from prose."""
class ReasoningStream:
    markers = {'<think>': True, '</think>': False, '<analysis>': True, '</analysis>': False,
               '<|channel|>analysis<|message|>': True, '<|channel|>final<|message|>': False}

    def __init__(self, send, thinking=False):
        self.send = send; self.thinking = thinking; self.buffer = ''; self.text = ''; self.reasoning = ''

    def write(self, text, reasoning=False):
        if not text: return
        if reasoning:
            self.reasoning += text; self.send(text, 'reasoning'); return
        self.buffer += text
        while self.buffer:
            matches = [(self.buffer.find(marker), marker) for marker in self.markers if marker in self.buffer]
            if matches:
                index, marker = min(matches)
                self._emit(self.buffer[:index]); self.thinking = self.markers[marker]
                self.buffer = self.buffer[index + len(marker):]; continue
            keep = max([0] + [n for marker in self.markers for n in range(1, len(marker)) if self.buffer.endswith(marker[:n])])
            self._emit(self.buffer[:-keep] if keep else self.buffer)
            self.buffer = self.buffer[-keep:] if keep else ''; break

    def _emit(self, text):
        if not text: return
        if self.thinking: self.reasoning += text
        else: self.text += text
        self.send(text, 'reasoning' if self.thinking else 'final')

    def finish(self):
        self._emit(self.buffer); self.buffer = ''
