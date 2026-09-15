"""工作流 HTTP 合同的独立进程夹具；只编码测试字节，不加载任何模型。"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import struct
import time
import wave
import zlib


def emit(kind, **values):
    print(json.dumps({'type': kind, **values}, ensure_ascii=False), flush=True)


def cancelled(*_):
    emit('error', code='CANCELLED', message='工作流合同夹具已确认取消')
    raise SystemExit(130)


parser = argparse.ArgumentParser()
parser.add_argument('--snapshot', type=Path, required=True)
parser.add_argument('--output-dir', type=Path, required=True)
args = parser.parse_args()
snapshot = json.loads(args.snapshot.read_text())
signal.signal(signal.SIGTERM, cancelled)
emit('phase', phase='workflow_fixture', message='只运行工作流文件合同，不执行模型')
assert snapshot.get('workflow_ref'), '合同夹具要求真实提交绑定的工作流来源'
prompt = snapshot['input'].get('prompt', '')
if prompt == '测试：等待取消':
    for _ in range(600):
        time.sleep(0.1)
if prompt == '测试：执行失败':
    emit('error', code='FIXTURE_FAILED', message='工作流测试预定失败')
    raise SystemExit(3)

result = args.output_dir / 'result'
result.mkdir(parents=True, exist_ok=False)
kind = snapshot['kind']
if kind == 'image':
    def chunk(name, data):
        return struct.pack('>I', len(data)) + name + data + struct.pack('>I', zlib.crc32(name + data) & 0xffffffff)
    row = b'\0' + bytes([113, 127, 211]) * 8
    raw = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 8, 8, 8, 2, 0, 0, 0))
    raw += chunk(b'IDAT', zlib.compress(row * 8)) + chunk(b'IEND', b'')
    primary, mime = result / 'image.png', 'image/png'
    primary.write_bytes(raw)
elif kind == 'video':
    def box(name, body):
        return struct.pack('>I', len(body) + 8) + name + body
    primary, mime = result / 'video.mp4', 'video/mp4'
    primary.write_bytes(box(b'ftyp', b'isom\0\0\0\0isomiso2') + box(b'moov', b'fixture-index') + box(b'mdat', b'fixture-video'))
else:
    assert kind == 'audio'
    primary, mime = result / 'speech.wav', 'audio/wav'
    with wave.open(str(primary), 'wb') as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(24000)
        stream.writeframes(b'\0\0' * 240)
report = result / 'fixture-report.json'
report.write_text(json.dumps({'fixture_only': True, 'model_execution': False, 'pid': os.getpid(), 'snapshot_sha256': hashlib.sha256(args.snapshot.read_bytes()).hexdigest(), 'workflow_ref': snapshot['workflow_ref'], 'input': snapshot['input']}, ensure_ascii=False))
artifacts = [{'path': path.relative_to(args.output_dir).as_posix(), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'media_type': media} for path, media in [(primary, mime), (report, 'application/json')]]
emit('completed', artifacts=artifacts, effective_config={**snapshot['runtime'], 'fixture_only': True, 'workflow_ref': snapshot['workflow_ref']})
