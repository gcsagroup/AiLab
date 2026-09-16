"""固定媒体模型与来源明确的 PNG 输入；分析和复制均不执行模型代码。"""

import hashlib
import json
import os
import re
import stat
import struct
import zlib
from pathlib import Path, PurePosixPath

from .assets import check_safetensors, regular_path, restricted_execution_boundary, safe_json, verify_manifest
from .media_model_cards import CARDS
from .storage import Fault, digest


def _bounded_bytes(path, maximum):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'rb') as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise Fault('PATH_NOT_ALLOWED', '只接受常规文件。')
        data = stream.read(maximum + 1)
    if len(data) > maximum:
        raise Fault('IMPORT_TOO_LARGE', '实际读取的媒体输入超过大小上限。')
    return data


def _json_entry(path, relative):
    data = _bounded_bytes(regular_path(path), 1024 * 1024)
    try:
        value = json.loads(data.decode('utf-8'))
    except (ValueError, UnicodeError) as error:
        raise Fault('DATA_SCHEMA_MISMATCH', '数据与配方必须为 UTF-8 JSON。') from error
    if not isinstance(value, dict):
        raise Fault('DATA_SCHEMA_MISMATCH', '数据与配方必须为 JSON 对象。')
    return value, {'path': relative, 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def media_model_manifest(path):
    path = regular_path(path)
    if not path.is_dir() or not (path / 'manifest.json').is_file():
        return None
    metadata = safe_json(regular_path(path / 'manifest.json'), maximum=1024 * 1024)
    repository = metadata.get('repo', metadata.get('repository'))
    card = next((item for item in CARDS if item['repo'] == repository), None)
    if card is None:
        if (path / 'model_index.json').exists() or metadata.get('schema_version') == 'kokoro-zh-v1':
            raise Fault('MODEL_UNVERIFIED', '此媒体模型不在当前已验证组合内。')
        return None
    # 固定身份包含清单本身；同时更改权重与自报摘要不能取得已验证模型身份。
    verify_manifest(path, card['files'])
    for item in card['files']:
        if item['path'].endswith('.safetensors'):
            check_safetensors(path / item['path'])
    official_torch = card['default_engine'] == 'kokoro'
    return {'manifest': card['files'], 'manifest_digest': digest(card['files']),
            'detected_format': card['format'], 'family': card['family'],
            'modality': card['modality'], 'default_engine': card['default_engine'],
            'model_config': {'model_type': card['family'], 'repository': card['repo'], 'revision': card['revision']},
            'metadata_manifest_digest': card['metadata_manifest_digest'],
            'total_bytes': sum(item['size'] for item in card['files']), 'file_count': len(card['files']),
            'loader': 'kokoro.fixed_official_weights_only_cpu' if official_torch else 'diffusers.fixed_local_safetensors',
            'trust_class': 'restricted_official_torch' if official_torch else 'restricted_weights',
            'execution_scope': {'network': False, 'custom_code': False, 'credentials': False},
            'execution_boundary': restricted_execution_boundary(),
            'license': card['license'], 'can_import': True, 'issues': [],
            'warnings': [{'message': '仅验证本地加载和生成功能，输出质量需另行检查。'}]}


def png_info(path):
    """检查 CRC、压缩流及扫描行边界；仅接收非隔行的 8-bit RGB/RGBA 静态 PNG。"""
    path = regular_path(path)
    if not path.is_file() or path.suffix.lower() != '.png' or not 45 <= path.stat().st_size <= 32 * 1024 * 1024:
        raise Fault('MEDIA_FORMAT_UNSUPPORTED', '请选择不超过 32 MiB 的 RGB 或 RGBA PNG 静态图片。')
    raw = _bounded_bytes(path, 32 * 1024 * 1024)
    if raw[:8] != b'\x89PNG\r\n\x1a\n':
        raise Fault('MEDIA_CORRUPT', 'PNG 文件标识无效。')
    cursor, chunks, compressed = 8, [], []
    width = height = channels = None
    ended_data = False
    while cursor < len(raw):
        if cursor + 12 > len(raw):
            raise Fault('MEDIA_CORRUPT', 'PNG 数据块不完整。')
        size, = struct.unpack('>I', raw[cursor:cursor + 4])
        kind = raw[cursor + 4:cursor + 8]
        end = cursor + 8 + size
        if end + 4 > len(raw) or not re.fullmatch(rb'[A-Za-z]{4}', kind) or kind[2] & 32:
            raise Fault('MEDIA_CORRUPT', 'PNG 数据块类型或长度无效。')
        body = raw[cursor + 8:end]
        checksum, = struct.unpack('>I', raw[end:end + 4])
        if zlib.crc32(kind + body) & 0xffffffff != checksum:
            raise Fault('MEDIA_CORRUPT', 'PNG 数据块校验失败。')
        cursor = end + 4
        if not chunks and kind != b'IHDR':
            raise Fault('MEDIA_CORRUPT', 'PNG 缺少首个图片头。')
        if kind == b'IHDR':
            if chunks or size != 13:
                raise Fault('MEDIA_CORRUPT', 'PNG 图片头重复或长度错误。')
            width, height, depth, colour, compression, filtering, interlace = struct.unpack('>IIBBBBB', body)
            if not 1 <= width <= 8192 or not 1 <= height <= 8192 or width * height > 16 * 1024 * 1024:
                raise Fault('MEDIA_TOO_LARGE', '图片尺寸不能超过 8192，且总像素不能超过 16M。')
            if depth != 8 or colour not in (2, 6) or compression != 0 or filtering != 0 or interlace != 0:
                raise Fault('MEDIA_FORMAT_UNSUPPORTED', '当前仅接收非隔行的 8-bit RGB/RGBA PNG，不进行隐含格式转换。')
            channels = 3 if colour == 2 else 4
        elif kind == b'IDAT':
            if ended_data:
                raise Fault('MEDIA_CORRUPT', 'PNG 图像数据块必须连续。')
            compressed.append(body)
        elif kind == b'IEND':
            if size or cursor != len(raw) or not compressed:
                raise Fault('MEDIA_CORRUPT', 'PNG 尾部无效、含额外内容或缺少图像数据。')
        elif kind in (b'acTL', b'fcTL', b'fdAT'):
            raise Fault('MEDIA_FORMAT_UNSUPPORTED', '当前输入要求静态 PNG，不接受动画。')
        elif not kind[0] & 32 and kind != b'PLTE':
            raise Fault('MEDIA_FORMAT_UNSUPPORTED', 'PNG 包含尚未支持的关键数据块。')
        elif kind == b'PLTE' and (compressed or size % 3 or not 3 <= size <= 768 or kind in chunks):
            raise Fault('MEDIA_CORRUPT', 'PNG 调色板无效。')
        if compressed and kind != b'IDAT':
            ended_data = True
        chunks.append(kind)
    if not chunks or chunks[-1] != b'IEND':
        raise Fault('MEDIA_CORRUPT', 'PNG 缺少结束块。')
    row_bytes = width * channels + 1
    expected = row_bytes * height
    try:
        decoder = zlib.decompressobj()
        data = decoder.decompress(b''.join(compressed), expected + 1)
    except zlib.error as error:
        raise Fault('MEDIA_CORRUPT', 'PNG 压缩图像数据损坏。') from error
    if len(data) != expected or decoder.unconsumed_tail or decoder.unused_data or not decoder.eof or any(data[index] > 4 for index in range(0, len(data), row_bytes)):
        raise Fault('MEDIA_CORRUPT', 'PNG 解压后的扫描行、滤波或图像长度不符。')
    return {'width': width, 'height': height, 'channels': channels, 'media_type': 'image/png',
            'sha256': hashlib.sha256(raw).hexdigest(), 'size': len(raw), 'decode_scope': 'PNG CRC、压缩流和扫描行验证；执行前由 Pillow 完整解码'}


def material_report(path):
    path = regular_path(path)
    info = png_info(path)
    manifest = [{'path': path.name, 'size': info['size'], 'sha256': info['sha256']}]
    return {**info, 'kind': 'image', 'manifest': manifest, 'manifest_digest': digest(manifest),
            'total_bytes': info['size'], 'file_count': 1, 'can_import': True, 'issues': [],
            'entrypoint': path.name, 'checks': {'file': 'passed', 'quality': 'not_run'}}


def _relative_file(root, value):
    if not isinstance(value, str) or not value or len(value) > 1024 or '\\' in value or '\x00' in value:
        raise Fault('DATA_SCHEMA_MISMATCH', '数据引用路径必须为目录内的相对路径。')
    relative = PurePosixPath(value)
    if relative.is_absolute() or any(part in ('', '.', '..') for part in value.split('/')):
        raise Fault('PATH_NOT_ALLOWED', '数据引用不能包含上级跳转、绝对路径或空路径。')
    path = regular_path(root / value)
    if not path.is_relative_to(root) or not path.is_file():
        raise Fault('PATH_NOT_ALLOWED', '数据引用必须是同目录内的常规文件。')
    return path


def image_dataset_report(path):
    path = regular_path(path)
    if not path.is_dir():
        raise Fault('DATA_SCHEMA_MISMATCH', '请选择同时包含 dataset.json 和图片的目录。')
    entry = _relative_file(path, 'dataset.json')
    dataset, entry_manifest = _json_entry(entry, 'dataset.json')
    samples = dataset.get('samples')
    if not isinstance(dataset.get('version'), str) or not dataset['version'].strip() or not isinstance(samples, list) or not 1 <= len(samples) <= 8:
        raise Fault('DATA_SCHEMA_MISMATCH', '图片数据需要非空 version 和 1—8 条 samples。')
    files = {'dataset.json': entry_manifest}
    paths = set()
    for record in samples:
        if not isinstance(record, dict) or any(not isinstance(record.get(field), str) or not record[field].strip() for field in ('path', 'caption', 'source', 'sha256')) or len(record['caption']) > 2000 or not re.fullmatch(r'[0-9a-f]{64}', record['sha256']):
            raise Fault('DATA_SCHEMA_MISMATCH', '每条图片数据需有相对路径、描述、来源说明和 SHA256。')
        source = _relative_file(path, record['path'])
        if record['path'] in paths:
            raise Fault('DATA_SCHEMA_MISMATCH', '图片数据存在重复路径，请明确样本划分。')
        paths.add(record['path'])
        info = png_info(source)
        if (info['width'], info['height'], info['channels']) != (512, 512, 3):
            raise Fault('DATA_SCHEMA_MISMATCH', '首个图片训练组合需要 512×512 RGB 原图，不静默裁剪或缩放。')
        if info['sha256'] != record['sha256']:
            raise Fault('SOURCE_CHANGED', '训练图片摘要与 dataset.json 不符。', 409)
        files[record['path']] = {'path': record['path'], 'size': info['size'], 'sha256': info['sha256']}
        if 'generation_recipe' in record:
            recipe = _relative_file(path, record['generation_recipe'])
            if recipe.suffix.lower() != '.json':
                raise Fault('DATA_SCHEMA_MISMATCH', '生成配方引用必须为 JSON 文件。')
            _, files[record['generation_recipe']] = _json_entry(recipe, record['generation_recipe'])
    manifest = sorted(files.values(), key=lambda item: item['path'])
    return {'schema': 'image_caption_v1', 'entrypoint': 'dataset.json', 'manifest': manifest,
            'manifest_digest': digest(manifest), 'sha256': files['dataset.json']['sha256'],
            'total_bytes': sum(item['size'] for item in manifest), 'file_count': len(manifest),
            'sample_count': len(samples), 'checks': {'structure': 'passed', 'images': 'passed', 'captions': 'tokenization_pending', 'quality': 'not_run', 'source': 'declared_not_independently_verified'},
            'selection_scope': '只复制 dataset.json 明确引用的图片与生成配方；不复制目录内其它文件。',
            'warnings': [{'message': '描述与画面是否一致、数据使用权仍需人工检查；结构检查不代表质量验收。'}],
            'can_import': True, 'issues': []}
