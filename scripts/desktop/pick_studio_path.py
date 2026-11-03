"""Native resource picker for the local Vite preview (no file upload/copy)."""
import json
import sys
from pathlib import Path


def main():
    import tkinter as tk
    from tkinter import filedialog
    mode = sys.argv[1]
    if mode not in ('directory', 'file', 'gguf'):
        raise ValueError('Unsupported picker mode')
    root = tk.Tk(); root.withdraw()
    try:
        root.attributes('-topmost', True)
        if mode == 'directory':
            selected = filedialog.askdirectory(parent=root, title='选择本地资源目录', mustexist=True)
        else:
            selected = filedialog.askopenfilename(parent=root, title='选择 GGUF 模型权重' if mode == 'gguf' else '选择本地资源',
                filetypes=[('GGUF 模型', '*.gguf')] if mode == 'gguf' else [('所有文件', '*')])
        if selected and mode == 'gguf' and Path(selected).suffix.lower() != '.gguf':
            raise ValueError('请选择 .gguf 模型文件')
        print(json.dumps(str(Path(selected).resolve()) if selected else None, ensure_ascii=True))
    finally:
        root.destroy()


if __name__ == '__main__': main()
