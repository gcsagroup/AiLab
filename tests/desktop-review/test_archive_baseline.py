"""归档工具只读清单与无覆盖边界；完整签名 App 另行实际运行。"""

import importlib.util
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/desktop"))
spec = importlib.util.spec_from_file_location("archive_baseline", ROOT / "scripts/desktop/archive_baseline.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_inventory_tracks_bytes_modes_and_internal_links_without_writing(tmp_path):
    app = tmp_path / "代表性.app"; app.mkdir()
    original = app / "原文件"; original.write_bytes(b"original"); original.chmod(0o400)
    (app / "内部链接").symlink_to("原文件")
    before = original.stat().st_mtime_ns
    result = module.inventory(app)
    assert result["原文件"]["sha256"] == module.sha256(original)
    assert result["原文件"]["mode"] == 0o400
    assert result["内部链接"]["target"] == "原文件"
    assert original.stat().st_mtime_ns == before


def test_inventory_rejects_external_link(tmp_path):
    app = tmp_path / "代表性.app"; app.mkdir()
    private = tmp_path / "外部资料"; private.write_bytes(b"outside")
    (app / "不允许的链接").symlink_to(private)
    with pytest.raises(ValueError, match="越出"):
        module.inventory(app)


def test_existing_archive_is_preserved_before_any_signature_or_copy(tmp_path, monkeypatch):
    output = tmp_path / ".artifacts/desktop/upgrade-baseline"; output.mkdir(parents=True)
    marker = output / "原归档"; marker.write_text("不可覆盖")
    monkeypatch.setattr(module, "signature", lambda *_: pytest.fail("已有归档时不应开始复制"))
    with pytest.raises(FileExistsError):
        module.archive(tmp_path, output)
    assert marker.read_text() == "不可覆盖"
