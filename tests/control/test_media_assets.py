"""媒体输入采用真实编码字节，覆盖损坏、越界、隐含转换与模型伪报身份。"""

import copy
import hashlib
import json
from pathlib import Path
import struct
import sys
import zlib

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'services/control'))
from ailab_control.assets import copy_asset, verify_manifest
from ailab_control.media_assets import image_dataset_report, material_report, media_model_manifest, png_info
from ailab_control.storage import Fault, digest


def chunk(kind, data):
    return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)


def png(path, width=512, height=512, channels=3, row_filter=0, raw_suffix=b''):
    image = bytes([row_filter]) + bytes([113, 127, 211, 255][:channels]) * width
    data = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2 if channels == 3 else 6, 0, 0, 0))
    data += chunk(b'IDAT', zlib.compress(image * height + raw_suffix)) + chunk(b'IEND', b'')
    path.write_bytes(data)
    return path


def dataset(path):
    path.mkdir()
    image = png(path / '样本.png')
    data = {'version': '技术夹具-v1', 'samples': [{'path': image.name, 'caption': '蓝色产品，测试用', 'source': '测试代码生成；不是模型质量证据', 'sha256': hashlib.sha256(image.read_bytes()).hexdigest()}]}
    (path / 'dataset.json').write_text(json.dumps(data, ensure_ascii=False))
    return data


def test_material_checks_real_png_and_copies_without_source_change(tmp_path):
    path = png(tmp_path / '真实结构 PNG.png', width=9, height=7, channels=4)
    before = path.read_bytes()
    report = material_report(path)
    assert (report['width'], report['height'], report['channels']) == (9, 7, 4)
    assert report['manifest_digest'] == digest(report['manifest'])
    assets = tmp_path / 'assets'
    assets.mkdir()
    copied = copy_asset(path, assets, report['manifest'], report['manifest_digest'])
    verify_manifest(copied, report['manifest'])
    assert path.read_bytes() == before


@pytest.mark.parametrize('corruption', ['crc', 'truncated', 'trailing', 'filter', 'overlong_raw', 'animation', 'missing_end', 'unknown_critical', 'bomb_dimensions'])
def test_invalid_png_rejected_before_registration(tmp_path, corruption):
    path = png(tmp_path / '坏图.png', width=8, height=8)
    raw = path.read_bytes()
    if corruption == 'crc':
        raw = raw[:40] + bytes([raw[40] ^ 1]) + raw[41:]
    elif corruption == 'truncated':
        raw = raw[:-3]
    elif corruption == 'trailing':
        raw += b'unreferenced data'
    elif corruption == 'filter':
        png(path, width=8, height=8, row_filter=5)
        raw = path.read_bytes()
    elif corruption == 'overlong_raw':
        png(path, width=8, height=8, raw_suffix=b'x' * 10000)
        raw = path.read_bytes()
    elif corruption == 'animation':
        raw = raw[:33] + chunk(b'acTL', struct.pack('>II', 1, 0)) + raw[33:]
    elif corruption == 'missing_end':
        raw = raw[:-12]
    elif corruption == 'unknown_critical':
        raw = raw[:33] + chunk(b'ABCD', b'') + raw[33:]
    elif corruption == 'bomb_dimensions':
        raw = raw[:8] + chunk(b'IHDR', struct.pack('>IIBBBBB', 8192, 8192, 8, 2, 0, 0, 0)) + raw[33:]
    path.write_bytes(raw)
    with pytest.raises(Fault):
        material_report(path)


def test_png_symlink_rejected(tmp_path):
    real = png(tmp_path / 'real.png')
    link = tmp_path / 'linked.png'
    link.symlink_to(real)
    with pytest.raises(Fault, match='符号链接'):
        png_info(link)


def test_png_growth_after_size_check_is_bounded(tmp_path, monkeypatch):
    from ailab_control import media_assets
    path = png(tmp_path / '增长.png', width=8, height=8)
    original_open = media_assets.os.open
    opened = False
    def changing_open(value, *args, **kwargs):
        nonlocal opened
        if Path(value) == path and not opened:
            opened = True
            raw = path.read_bytes()
            path.write_bytes(raw[:-12] + chunk(b'tEXt', b'x' * (32 * 1024 * 1024)) + raw[-12:])
        return original_open(value, *args, **kwargs)
    monkeypatch.setattr(media_assets.os, 'open', changing_open)
    with pytest.raises(Fault, match='超过'):
        png_info(path)


def test_dataset_plan_hash_always_describes_the_parsed_bytes(tmp_path, monkeypatch):
    from ailab_control import media_assets
    source = tmp_path / '训练资料'
    data = dataset(source)
    original_bytes = (source / 'dataset.json').read_bytes()
    original_png = media_assets.png_info
    def replace_after_parsing(path):
        changed = copy.deepcopy(data)
        changed['samples'][0]['path'] = '../outside.png'
        (source / 'dataset.json').write_text(json.dumps(changed, ensure_ascii=False))
        return original_png(path)
    monkeypatch.setattr(media_assets, 'png_info', replace_after_parsing)
    report = image_dataset_report(source)
    entry = next(item for item in report['manifest'] if item['path'] == 'dataset.json')
    assert entry['sha256'] == hashlib.sha256(original_bytes).hexdigest()
    assert entry['sha256'] != hashlib.sha256((source / 'dataset.json').read_bytes()).hexdigest()
    assets = tmp_path / 'assets'
    assets.mkdir()
    with pytest.raises(Fault, match='发生变化'):
        copy_asset(source, assets, report['manifest'], report['manifest_digest'])
    assert not (assets / report['manifest_digest']).exists()


def test_image_dataset_copies_explicit_dependencies_and_keeps_extras(tmp_path):
    source = tmp_path / '训练资料'
    data = dataset(source)
    data['samples'][0]['generation_recipe'] = 'recipe.json'
    (source / 'recipe.json').write_text('{"来源":"确定性测试图片"}')
    (source / 'dataset.json').write_text(json.dumps(data, ensure_ascii=False))
    (source / '不可导入.txt').write_text('保留其它研究资产')
    report = image_dataset_report(source)
    assert {item['path'] for item in report['manifest']} == {'dataset.json', '样本.png', 'recipe.json'}
    assert report['sample_count'] == 1 and report['checks']['quality'] == 'not_run'
    assets = tmp_path / 'assets'
    assets.mkdir()
    copied = copy_asset(source, assets, report['manifest'], report['manifest_digest'])
    verify_manifest(copied, report['manifest'])
    assert (source / '不可导入.txt').exists() and not (copied / '不可导入.txt').exists()


@pytest.mark.parametrize('invalid', ['path_escape', 'symlink', 'duplicate', 'bad_hash', 'missing_caption', 'missing_source', 'wrong_size', 'rgba', 'recipe_escape', 'file_instead_directory'])
def test_image_dataset_refuses_unsafe_or_incompatible_samples(tmp_path, invalid):
    source = tmp_path / '训练资料'
    data = dataset(source)
    record = data['samples'][0]
    if invalid == 'path_escape':
        record['path'] = '../样本.png'
    elif invalid == 'symlink':
        (source / '样本.png').rename(tmp_path / 'external.png')
        (source / '样本.png').symlink_to(tmp_path / 'external.png')
    elif invalid == 'duplicate':
        data['samples'].append(copy.deepcopy(record))
    elif invalid == 'bad_hash':
        record['sha256'] = '0' * 64
    elif invalid == 'missing_caption':
        record['caption'] = ' '
    elif invalid == 'missing_source':
        del record['source']
    elif invalid in {'wrong_size', 'rgba'}:
        png(source / '样本.png', width=256 if invalid == 'wrong_size' else 512, channels=4 if invalid == 'rgba' else 3)
        record['sha256'] = hashlib.sha256((source / '样本.png').read_bytes()).hexdigest()
    elif invalid == 'recipe_escape':
        record['generation_recipe'] = '../recipe.json'
    (source / 'dataset.json').write_text(json.dumps(data, ensure_ascii=False))
    with pytest.raises(Fault):
        image_dataset_report(source / 'dataset.json' if invalid == 'file_instead_directory' else source)


def test_fixed_model_cannot_gain_identity_by_rewriting_its_own_manifest(tmp_path, monkeypatch):
    from ailab_control import media_assets
    root = tmp_path / '模型'
    root.mkdir()
    (root / 'manifest.json').write_text('{"repo":"test/frozen-model"}')
    (root / 'weights.pth').write_bytes('不会执行的合同字节'.encode())
    files = [{'path': item.name, 'size': item.stat().st_size, 'sha256': hashlib.sha256(item.read_bytes()).hexdigest()} for item in sorted(root.iterdir())]
    card = {'repo': 'test/frozen-model', 'revision': 'fixed', 'family': 'kokoro-82m', 'format': 'torch-restricted-official', 'files': files, 'modality': 'audio', 'default_engine': 'kokoro', 'license': '测试夹具', 'metadata_manifest_digest': digest(files)}
    monkeypatch.setattr(media_assets, 'CARDS', [card])
    report = media_model_manifest(root)
    assert report['modality'] == 'audio' and report['execution_scope']['custom_code'] is False
    (root / 'weights.pth').write_bytes('替换后的测试字节'.encode())
    (root / 'manifest.json').write_text(json.dumps({'repo': 'test/frozen-model', 'sha256': hashlib.sha256((root / 'weights.pth').read_bytes()).hexdigest()}))
    with pytest.raises(Fault, match='摘要'):
        media_model_manifest(root)


def test_unknown_diffusers_manifest_does_not_fall_back_to_broad_loader(tmp_path):
    (tmp_path / 'manifest.json').write_text('{"repo":"unknown/model"}')
    (tmp_path / 'model_index.json').write_text('{}')
    with pytest.raises(Fault, match='组合'):
        media_model_manifest(tmp_path)
