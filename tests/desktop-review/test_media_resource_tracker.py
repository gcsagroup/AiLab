"""冻结媒体入口可运行资源追踪器，但不能接受任意 -c 内容。"""

import os
from pathlib import Path
import subprocess
import sys

import pytest

ENTRY = Path(__file__).resolve().parents[2] / "scripts/desktop/media_entry.py"


@pytest.fixture
def launcher(tmp_path):
    target = tmp_path / "固定入口.py"
    target.write_text("import importlib.util\nspec = importlib.util.spec_from_file_location('entry', " + repr(str(ENTRY)) + ")\nentry = importlib.util.module_from_spec(spec)\nspec.loader.exec_module(entry)\nraise SystemExit(entry.main())\n")
    return target


@pytest.mark.parametrize("flags", [[], ["-B"]])
def test_tracker_runs_on_real_inherited_pipe_and_exits_on_eof(launcher, flags):
    reader, writer = os.pipe()
    child = subprocess.Popen([sys.executable, str(launcher), *flags, "-c", f"from multiprocessing.resource_tracker import main;main({reader})"], pass_fds=[reader], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    os.close(reader)
    os.write(writer, b"PROBE:0:noop\n")
    os.close(writer)
    stdout, stderr = child.communicate(timeout=10)
    assert child.returncode == 0 and not stdout and not stderr


@pytest.mark.parametrize("change", ["suffix", "prefix", "unknown-flag", "extra-argument", "write-pipe", "regular-file"])
def test_tracker_rejects_arbitrary_text_flags_and_non_read_pipe(launcher, tmp_path, change):
    reader, writer = os.pipe()
    marker = tmp_path / "不允许执行"
    regular = os.open(launcher, os.O_RDONLY)
    descriptor = writer if change == "write-pipe" else regular if change == "regular-file" else reader
    script = f"from multiprocessing.resource_tracker import main;main({descriptor})"
    if change == "suffix":
        script += f";open({str(marker)!r},'w').write('执行')"
    elif change == "prefix":
        script = f"open({str(marker)!r},'w').write('执行');" + script
    arguments = (["-E"] if change == "unknown-flag" else []) + ["-c", script] + (["extra"] if change == "extra-argument" else [])
    try:
        result = subprocess.run([sys.executable, str(launcher), *arguments], pass_fds=[reader, writer, regular], capture_output=True, timeout=10)
        assert result.returncode != 0 and not marker.exists()
    finally:
        for descriptor in [reader, writer, regular]:
            os.close(descriptor)


def test_tracker_matches_complete_trusted_frozen_flags(monkeypatch):
    import importlib.util
    from multiprocessing import resource_tracker, util
    spec = importlib.util.spec_from_file_location("entry_tracker_flags", ENTRY)
    entry = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(entry)
    expected = ["-B", "-S", "-I"]
    monkeypatch.setattr(util, "_args_from_interpreter_flags", lambda: expected)
    tracked = []
    monkeypatch.setattr(resource_tracker, "main", lambda descriptor: tracked.append(descriptor))
    reader, writer = os.pipe()
    script = f"from multiprocessing.resource_tracker import main;main({reader})"
    try:
        assert entry.resource_tracker([*expected, "-c", script]) == 0
        assert tracked == [reader]
        for flags in [["-S"], ["-S", "-B", "-I"], [*expected, "-E"], [*expected, "-X", "dev"]]:
            with pytest.raises(ValueError):
                entry.resource_tracker([*flags, "-c", script])
        assert tracked == [reader]
    finally:
        os.close(reader)
        os.close(writer)
