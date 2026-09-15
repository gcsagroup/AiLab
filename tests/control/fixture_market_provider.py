"""独立受控测试提供方：真实 HTTP、审批记录和 Range 字节；不会自动批准。"""

import argparse
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import socket
import threading
import time
from urllib.parse import parse_qs, unquote, urlsplit


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


def write(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_bytes(encoded(value))
    temporary.replace(path)


def decide(state, request_id, status, provider_text, expires_at=None):
    if status not in {'waiting', 'approved', 'denied', 'expired', 'revoked'} or not re.fullmatch('access-[0-9a-f]{64}', request_id):
        raise ValueError('提供方审批参数无效')
    path = state / (request_id + '.json')
    value = json.loads(path.read_text())
    value['response'].update(status=status, provider_text=provider_text, updated_at=datetime.now(timezone.utc).isoformat(), expires_at=expires_at, revision=value['response']['revision'] + 1)
    write(path, value)
    return value['response']


class Provider(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, root, state, port=0):
        self.root, self.state = root.resolve(), state.resolve()
        self.state.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.chunk_delay = 0
        self.received_requests, self.ranges = [], []
        self.redirect = False
        self.disconnect_once_after = None
        self.bad_range = False
        super().__init__(('127.0.0.1', port), Handler)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, value, status=200):
        body = encoded(value)
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def catalog(self):
        return json.loads((self.server.root / 'catalog.json').read_text())

    def do_POST(self):
        if self.path != '/v1/access':
            return self.reply({'error': '不存在'}, 404)
        try:
            length = int(self.headers.get('Content-Length', '0'))
            assert 0 < length <= 20000
            payload = json.loads(self.rfile.read(length))
            assert set(payload) == {'provider_id', 'dataset_key', 'version', 'version_digest', 'purpose', 'user_statement', 'request_key'}
            catalog = self.catalog()
            entry = next(item for item in catalog['versions'] if item['dataset_key'] == payload['dataset_key'] and item['version'] == payload['version'])
            assert payload['provider_id'] == catalog['provider_id'] and entry['access'] == 'restricted'
            assert hashlib.sha256(encoded(entry)).hexdigest() == payload['version_digest']
            request_id = 'access-' + hashlib.sha256(payload['request_key'].encode()).hexdigest()
            path = self.server.state / (request_id + '.json')
            with self.server.lock:
                if path.exists():
                    previous = json.loads(path.read_text())
                    assert previous['sent'] == payload
                    return self.reply(previous['response'])
                response = {name: payload[name] for name in ('provider_id', 'dataset_key', 'version', 'version_digest')}
                response.update(request_id=request_id, status='waiting', provider_text='受控测试提供方已收到申请，等待提供方操作员处理。', updated_at=datetime.now(timezone.utc).isoformat(), expires_at=None, revision=1)
                write(path, {'sent': payload, 'response': response})
                self.server.received_requests.append(payload)
                return self.reply(response)
        except (ValueError, AssertionError, KeyError, StopIteration):
            self.reply({'error': '申请字段或版本不符'}, 409)

    def do_GET(self):
        parsed = urlsplit(self.path)
        if self.server.redirect:
            self.send_response(302)
            self.send_header('Location', 'http://127.0.0.1:1/forbidden')
            self.end_headers()
            return
        if parsed.path == '/v1/catalog':
            return self.reply(self.catalog())
        if re.fullmatch('/v1/access/access-[0-9a-f]{64}', parsed.path):
            path = self.server.state / (parsed.path.rsplit('/', 1)[-1] + '.json')
            return self.reply(json.loads(path.read_text())['response']) if path.is_file() else self.reply({'error': '申请不存在'}, 404)
        if not parsed.path.startswith('/v1/files/'):
            return self.reply({'error': '不存在'}, 404)
        try:
            parts = [unquote(part) for part in parsed.path[len('/v1/files/'):].split('/')]
            assert all(part and part not in {'.', '..'} and '/' not in part and '\\' not in part for part in parts)
            dataset_key, version, *file_parts = parts
            entry = next(item for item in self.catalog()['versions'] if item['dataset_key'] == dataset_key and item['version'] == version)
            relative = '/'.join(file_parts)
            assert any(item['path'] == relative for item in entry['files'])
            if entry['access'] == 'restricted':
                request_id = parse_qs(parsed.query).get('access_id', [''])[0]
                assert re.fullmatch('access-[0-9a-f]{64}', request_id)
                approval = json.loads((self.server.state / (request_id + '.json')).read_text())['response']
                assert approval['status'] == 'approved' and approval['dataset_key'] == dataset_key and approval['version'] == version
                assert approval['expires_at'] is None or datetime.fromisoformat(approval['expires_at']) > datetime.now(timezone.utc)
            path = self.server.root / 'files' / dataset_key / version / relative
            assert path.resolve().is_relative_to(self.server.root) and path.is_file() and not path.is_symlink()
            size = path.stat().st_size
            match = re.fullmatch('bytes=([0-9]+)-', self.headers.get('Range', ''))
            assert match and int(match[1]) < size
            start = int(match[1])
            self.server.ranges.append({'path': relative, 'offset': start})
            self.send_response(206)
            self.send_header('Content-Range', f'bytes {start}-{size - 1}/{size + int(self.server.bad_range)}')
            self.send_header('Content-Length', str(size - start))
            self.end_headers()
            with path.open('rb') as stream:
                stream.seek(start)
                sent = 0
                while chunk := stream.read(16384):
                    self.wfile.write(chunk)
                    self.wfile.flush()
                    sent += len(chunk)
                    if self.server.disconnect_once_after and sent >= self.server.disconnect_once_after:
                        self.server.disconnect_once_after = None
                        self.connection.shutdown(socket.SHUT_RDWR)
                        self.connection.close()
                        return
                    if self.server.chunk_delay:
                        time.sleep(self.server.chunk_delay)
        except (ValueError, AssertionError, KeyError, StopIteration, FileNotFoundError):
            self.reply({'error': '访问未获准或文件范围不符'}, 403)
        except (BrokenPipeError, ConnectionResetError):
            pass


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--port', type=int, default=0)
    parser.add_argument('--chunk-delay', type=float, default=0)
    parser.add_argument('--decision')
    parser.add_argument('--status', choices=['waiting', 'approved', 'denied', 'expired', 'revoked'])
    parser.add_argument('--provider-text')
    parser.add_argument('--expires-at')
    args = parser.parse_args()
    if args.decision:
        if not args.status or not args.provider_text:
            parser.error('审批必须由提供方操作员填写状态和原文。')
        print(json.dumps(decide(args.state, args.decision, args.status, args.provider_text, args.expires_at), ensure_ascii=False))
    else:
        provider = Provider(args.root, args.state, args.port)
        if not 0 <= args.chunk_delay <= 1:
            parser.error('测试分块延迟必须位于 0 至 1 秒。')
        provider.chunk_delay = args.chunk_delay
        print(json.dumps({'source_label': '受控测试来源', 'origin': f'http://127.0.0.1:{provider.server_port}', 'pid': __import__('os').getpid()}, ensure_ascii=False), flush=True)
        provider.serve_forever()
