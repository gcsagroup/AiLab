import importlib.util
import json
from pathlib import Path
import sys
from unittest.mock import Mock

import pytest


@pytest.mark.parametrize('selection', ['', 'local.gguf'])
def test_gguf_picker_selection_or_cancel(monkeypatch, capsys, tmp_path, selection):
    tk = pytest.importorskip('tkinter')
    from tkinter import filedialog
    script = Path(__file__).resolve().parents[2] / 'scripts/desktop/pick_studio_path.py'
    spec = importlib.util.spec_from_file_location('studio_picker', script)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    root = Mock(); monkeypatch.setattr(tk, 'Tk', lambda: root)
    selected = str(tmp_path / selection) if selection else ''
    choose = Mock(return_value=selected); monkeypatch.setattr(filedialog, 'askopenfilename', choose)
    monkeypatch.setattr(sys, 'argv', [str(script), 'gguf'])
    module.main()
    assert json.loads(capsys.readouterr().out) == (str(Path(selected).resolve()) if selection else None)
    assert choose.call_args.kwargs['filetypes'] == [('GGUF 模型', '*.gguf')]
    root.destroy.assert_called_once()
