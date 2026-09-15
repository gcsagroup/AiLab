"""只在新回环端口以临时 CA 验证真正 TLS；不改系统信任，不运行模型。"""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import selectors
import signal
import socket
import sqlite3
import ssl
import subprocess
import sys
import threading
import time
from contextlib import contextmanager

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'services/control'))
sys.path.insert(0, str(ROOT))
from ailab_control.remote import client as client_module
from ailab_control.remote.client import LoopbackClient, LoopbackTarget
from ailab_control.remote.protocol import ProtocolError, canonical_origin, digest, file_hash, MAX_CHUNK
from ailab_control.remote.server import Executor


EXECUTOR = 'executor-' + 'a' * 32
TOKEN = 'T' * 40


def command(argv, cwd):
    result = subprocess.run(['/usr/bin/openssl', *argv], cwd=cwd, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr


@pytest.fixture(scope='module')
def certificates(tmp_path_factory):
    root = tmp_path_factory.mktemp('独立TLS证书')
    (root / 'index').write_text(''); (root / 'serial').write_text('01\n')
    command(['req', '-new', '-x509', '-newkey', 'rsa:2048', '-nodes', '-keyout', 'ca.key', '-out', 'ca.pem',
             '-days', '2', '-subj', '/CN=AILab ephemeral test CA'], root)
    for name, san, expired in [('valid', 'IP:127.0.0.1,DNS:localhost', False),
                               ('wrong-host', 'DNS:elsewhere.invalid', False), ('expired', 'IP:127.0.0.1', True)]:
        command(['req', '-new', '-newkey', 'rsa:2048', '-nodes', '-keyout', name + '.key', '-out', name + '.csr',
                 '-subj', '/CN=AILab ephemeral TLS server'], root)
        config = root / (name + '.cnf')
        config.write_text(f'''[ca]
default_ca = local
[local]
database = {root / 'index'}
serial = {root / 'serial'}
new_certs_dir = {root}
certificate = {root / 'ca.pem'}
private_key = {root / 'ca.key'}
default_md = sha256
default_days = 1
policy = policy
unique_subject = no
x509_extensions = server
[policy]
commonName = supplied
[server]
basicConstraints = critical, CA:FALSE
keyUsage = critical, digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth
subjectAltName = {san}
''')
        args = ['ca', '-batch', '-config', str(config), '-in', name + '.csr', '-out', name + '.pem', '-notext']
        if expired:
            args += ['-startdate', '20200101000000Z', '-enddate', '20200102000000Z']
        command(args, root)
        (root / (name + '.key')).chmod(0o600)
    return root


def trusted_context(certificates):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_verify_locations(cafile=str(certificates / 'ca.pem'))
    return context


@pytest.fixture
def test_trust(monkeypatch, certificates):
    # 仅本测试进程替换构造器；产品没有私有 CA 参数或环境变量开关。
    monkeypatch.setattr(client_module, 'create_tls_context', lambda: trusted_context(certificates))


class TLSServer:
    def __init__(self, root, certificates):
        self.root, self.certificates = root, certificates
        self.data, self.token_file = root / '独立执行库', root / '临时凭证'
        root.mkdir(parents=True, exist_ok=True)
        self.token_file.write_text(TOKEN); self.token_file.chmod(0o600)
        self.port, self.process, self.error = 0, None, None
        self.certificate_name = 'valid'
        self.started_pids = []
        self.stop_receipts = []
        self.start()

    def argv(self):
        return [sys.executable, '-m', 'ailab_control.remote', '--data-dir', str(self.data), '--token-file', str(self.token_file),
                '--port', str(self.port), '--https', '--bind', '127.0.0.1', '--cert-file', str(self.certificates / (self.certificate_name + '.pem')),
                '--key-file', str(self.certificates / (self.certificate_name + '.key'))]

    def start(self, verify_identity=True):
        self.error = (self.root / f'stderr-{len(self.started_pids)}.log').open('wb')
        self.process = subprocess.Popen(self.argv(), cwd=self.root,
            env={'PATH': '/usr/bin:/bin', 'PYTHONPATH': str(ROOT / 'services/control'), 'PYTHONDONTWRITEBYTECODE': '1'},
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=self.error, text=True, start_new_session=True)
        self.started_pids.append(self.process.pid)
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(self.process.stdout, selectors.EVENT_READ)
                assert selector.select(10), 'TLS 执行器没有启动回执'
                raw = self.process.stdout.readline()
                assert raw, (self.root / self.error.name).read_text()
                self.facts = json.loads(raw)
            self.port, self.executor_id = self.facts['port'], self.facts['executor_id']
            assert self.facts['transport'] == 'https' and self.facts['validation_scope'] == 'https_protocol_only'
            self.client = LoopbackClient(LoopbackTarget(f'https://127.0.0.1:{self.port}', self.executor_id, TOKEN, transport='https'), self.root / '连接记录', timeout=2)
            if not verify_identity:
                return
            deadline = time.monotonic() + 5
            while True:
                try:
                    self.client.identity(); break
                except ProtocolError:
                    if time.monotonic() > deadline: raise
                    time.sleep(.02)
        except BaseException:
            self.stop(); raise

    def stop(self):
        forced = False
        if self.process and self.process.poll() is None:
            self.process.send_signal(signal.SIGTERM)
            try: self.process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                forced = True
                os.killpg(self.process.pid, signal.SIGKILL); self.process.wait(timeout=3)
        if self.process and self.process.stdout: self.process.stdout.close()
        if self.error: self.error.close()
        if self.process:
            if not any(value['pid'] == self.process.pid for value in self.stop_receipts):
                self.stop_receipts.append({'pid': self.process.pid, 'returncode': self.process.returncode, 'forced_kill': forced})
            (self.root / '服务停止回执.json').write_text(json.dumps(self.stop_receipts, ensure_ascii=False, indent=2) + '\n')
            with pytest.raises(ProcessLookupError): os.killpg(self.process.pid, 0)
            assert not forced, '超时强制回收已完成，但不计作正常退出通过'
            assert self.process.returncode == 0


@pytest.fixture
def server(tmp_path, certificates, test_trust):
    value = TLSServer(tmp_path / '真正TLS服务', certificates)
    try: yield value
    finally: value.stop()


def wait_terminal(server, attempt_id):
    deadline = time.monotonic() + 12
    while True:
        value = server.client.sync(attempt_id)
        if value.get('state') in {'succeeded', 'failed', 'cancelled'} and not value.get('has_more_events'):
            return value
        assert time.monotonic() < deadline, value
        time.sleep(.025)


def copy_snapshot(server, blob, steps=2, delay=1):
    return {'schema_version': 1, 'executor_id': server.executor_id, 'attempt_id': 'attempt-' + secrets.token_hex(16),
            'transport': 'https', 'adapter_id': 'protocol-copy', 'operation': 'copy', 'inputs': [blob],
            'runtime': {'steps': steps, 'step_delay_ms': delay}}


def test_real_tls_partial_upload_recollect_and_restart_keep_same_attempt(server, tmp_path, monkeypatch):
    directory = tmp_path / '授权输入'; directory.mkdir()
    path = directory / '代表输入.bin'; content = b'HTTPS resume original bytes\n' * 81000; path.write_bytes(content)
    sha = file_hash(path)
    partial = server.client._request('PUT', f'/blobs/{sha}?size={len(content)}&offset=0', content=content[:MAX_CHUNK])
    assert partial['offset'] == MAX_CHUNK and not partial['complete']
    blob = server.client.upload(path, [directory])
    snapshot = copy_snapshot(server, blob)
    attempt = server.client.submit(snapshot, 'one-original-attempt')
    original = wait_terminal(server, attempt['id'])
    assert original['state'] == 'succeeded' and original['run_count'] == 1
    assert original['transport'] == 'https' and original['validation_scope'] == 'https_protocol_only'
    assert original['snapshot_sha256'] == digest(snapshot)
    manifest = server.client.manifest(attempt['id'])
    assert manifest['manifest']['transport'] == 'https'
    destination = tmp_path / '独立补收'; destination.mkdir()
    collection = 'collection-' + secrets.token_hex(16)
    request, count = server.client._request, 0
    def interrupted(*args, **kwargs):
        nonlocal count
        if kwargs.get('binary'):
            count += 1
            if count == 2: raise ProtocolError('TLS_VERIFICATION_FAILED', '测试模拟连接中证书变化', 503)
        return request(*args, **kwargs)
    monkeypatch.setattr(server.client, '_request', interrupted)
    with pytest.raises(ProtocolError) as failure:
        server.client.collect(attempt['id'], manifest['manifest_sha256'], collection, destination)
    assert failure.value.code == 'TLS_VERIFICATION_FAILED'
    first = json.loads((server.client.state_dir / 'collections' / (collection + '.json')).read_text())
    assert first['status'] == 'failed' and first['failures'][-1]['code'] == 'TLS_VERIFICATION_FAILED'
    assert (destination / ('.' + collection + '.tmp') / 'file-000.bin.part').stat().st_size == MAX_CHUNK
    monkeypatch.setattr(server.client, '_request', request)
    server.stop(); server.start()
    assert server.executor_id == original['executor_id']
    receipt = server.client.collect(attempt['id'], manifest['manifest_sha256'], collection, destination)
    assert receipt['status'] == 'succeeded'
    assert (destination / collection / 'file-000.bin').read_bytes() == content
    assert server.client.attempt(attempt['id'])['run_count'] == 1
    assert server.client.manifest(attempt['id']) == manifest
    with sqlite3.connect(server.data / 'executor.sqlite3') as db:
        assert db.execute('SELECT count(*) FROM attempts').fetchone()[0] == 1


def test_real_tls_wrong_identity_never_reads_or_uploads_input(server, tmp_path, monkeypatch):
    client = LoopbackClient(LoopbackTarget(server.client.target.origin, EXECUTOR, TOKEN, transport='https'), tmp_path / '错误身份')
    def no_read(*_args, **_kwargs): raise AssertionError('身份失败前读取了输入文件')
    monkeypatch.setattr(client_module, 'safe_file', no_read)
    with pytest.raises(ProtocolError) as failed: client.upload(tmp_path / '不存在输入', [tmp_path])
    assert failed.value.code == 'EXECUTOR_IDENTITY_MISMATCH'
    with sqlite3.connect(server.data / 'executor.sqlite3') as db:
        assert db.execute('SELECT count(*) FROM blobs').fetchone()[0] == 0
        assert db.execute('SELECT count(*) FROM attempts').fetchone()[0] == 0


def test_real_tls_missing_or_mixed_snapshot_transport_rejected(server, tmp_path):
    path = tmp_path / 'small.txt'; path.write_text('代表小输入')
    blob = server.client.upload(path, [tmp_path])
    for transport in (None, 'loopback_http', 'other'):
        value = copy_snapshot(server, blob)
        if transport is None: value.pop('transport')
        else: value['transport'] = transport
        with pytest.raises(ProtocolError) as failed: server.client.submit(value, 'bad-' + str(transport))
        assert failed.value.code in {'TRANSPORT_MISMATCH', 'INVALID_TRANSPORT'}
    with sqlite3.connect(server.data / 'executor.sqlite3') as db:
        assert db.execute('SELECT count(*) FROM attempts').fetchone()[0] == 0


def test_real_tls_certificate_rotation_preserves_unknown_then_confirms_same_attempt(server, tmp_path):
    path = tmp_path / 'cancel.txt'; path.write_text('停止确认')
    blob = server.client.upload(path, [tmp_path])
    attempt = server.client.submit(copy_snapshot(server, blob, 100, 100), 'cancel-one')
    deadline = time.monotonic() + 5
    while True:
        current = server.client.sync(attempt['id'])
        if current['state'] == 'running': break
        assert time.monotonic() < deadline
        time.sleep(.01)
    # 原执行独立于网络服务继续；仅本临时服务换成同一测试CA的错误主机证书。
    server.stop(); server.certificate_name = 'wrong-host'; server.start(verify_identity=False)
    deadline = time.monotonic() + 3
    while True:
        disconnected = server.client.sync(attempt['id'])
        if disconnected.get('last_connection_error') == 'TLS_VERIFICATION_FAILED': break
        assert time.monotonic() < deadline
        time.sleep(.02)
    assert disconnected['id'] == attempt['id'] and disconnected['state'] == 'running'
    uncertain = server.client.cancel(attempt['id'], current['state_version'], 'cancel-original')
    assert uncertain['id'] == attempt['id'] and uncertain['stop_status'] == 'unknown'
    assert uncertain['connection_state'] == 'disconnected' and uncertain['state'] == 'running'
    server.stop(); server.certificate_name = 'valid'; server.start()
    current = server.client.sync(attempt['id'])
    server.client.cancel(attempt['id'], current['state_version'], 'cancel-original')
    final = wait_terminal(server, attempt['id'])
    assert final['state'] == 'cancelled' and final['stop_status'] == 'confirmed' and final['run_count'] == 1


@contextmanager
def counting_server(certificates, name='valid', location=None):
    received = []
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            received.append({'path': self.path, 'authorization': self.headers.get('Authorization')})
            body = json.dumps({'protocol_version': 1, 'executor_id': EXECUTOR, 'transport': 'https',
                               'validation_scope': 'https_protocol_only', 'network_remote_ready': True}).encode()
            self.send_response(302 if location else 200)
            if location: self.send_header('Location', location)
            self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
        def log_message(self, *_args): pass
    service = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    if name:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(str(certificates / (name + '.pem')), str(certificates / (name + '.key')))
        service.socket = context.wrap_socket(service.socket, server_side=True)
    thread = threading.Thread(target=service.serve_forever, daemon=True); thread.start()
    try: yield service, received
    finally:
        service.shutdown(); service.server_close(); thread.join(3)
        assert not thread.is_alive()


@pytest.mark.parametrize('certificate,trust', [('valid', False), ('wrong-host', True), ('expired', True)])
def test_actual_tls_certificate_failure_sends_no_http_auth_or_file(tmp_path, certificates, monkeypatch, certificate, trust):
    if trust:
        monkeypatch.setattr(client_module, 'create_tls_context', lambda: trusted_context(certificates))
    else:
        monkeypatch.setenv('SSL_CERT_FILE', str(certificates / 'ca.pem'))
        monkeypatch.setenv('SSL_CERT_DIR', str(certificates))
    with counting_server(certificates, certificate) as (service, received):
        client = LoopbackClient(LoopbackTarget(f'https://127.0.0.1:{service.server_port}', EXECUTOR, TOKEN, transport='https'), tmp_path / '连接')
        with pytest.raises(ProtocolError) as failure: client.upload(tmp_path / '未读取输入', [tmp_path])
        assert failure.value.code == 'TLS_VERIFICATION_FAILED'
        assert received == []


def test_actual_tls_redirect_never_forwards_bearer_or_downgrades(tmp_path, certificates, test_trust):
    with counting_server(certificates, None) as (sink, sink_requests):
        with counting_server(certificates, location=f'http://127.0.0.1:{sink.server_port}/stolen') as (source, requests):
            client = LoopbackClient(LoopbackTarget(f'https://127.0.0.1:{source.server_port}', EXECUTOR, TOKEN, transport='https'), tmp_path / '重定向')
            with pytest.raises(ProtocolError) as failure: client.identity()
            assert failure.value.code == 'REDIRECT_FORBIDDEN'
            assert requests == [{'path': '/executor/v1/identity', 'authorization': 'Bearer ' + TOKEN}]
            assert sink_requests == []


def test_actual_tls_ignores_proxy_environment(tmp_path, certificates, test_trust, monkeypatch):
    with counting_server(certificates, None) as (proxy, proxy_requests):
        for name in ('http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'all_proxy'):
            monkeypatch.setenv(name, f'http://127.0.0.1:{proxy.server_port}')
        monkeypatch.setenv('NO_PROXY', ''); monkeypatch.setenv('no_proxy', '')
        with counting_server(certificates) as (service, received):
            client = LoopbackClient(LoopbackTarget(f'https://127.0.0.1:{service.server_port}', EXECUTOR, TOKEN, transport='https'), tmp_path / '无代理')
            assert client.identity()['executor_id'] == EXECUTOR
            assert len(received) == 1 and proxy_requests == []


def test_plain_http_listener_never_receives_fallback_request(tmp_path, certificates, test_trust):
    # 原始 TCP 读取确认首字节为 TLS ClientHello，失败后没有 HTTP 或第二次降级连接。
    listener = socket.socket(); listener.bind(('127.0.0.1', 0)); listener.listen(2); listener.settimeout(1)
    received = []
    def receive():
        try:
            connection, _ = listener.accept()
            with connection:
                received.append(connection.recv(8192)); connection.sendall(b'HTTP/1.0 400 Bad Request\r\n\r\n')
            try:
                connection, _ = listener.accept()
                with connection: received.append(connection.recv(8192))
            except TimeoutError: pass
        finally: listener.close()
    thread = threading.Thread(target=receive, daemon=True); thread.start()
    client = LoopbackClient(LoopbackTarget(f'https://127.0.0.1:{listener.getsockname()[1]}', EXECUTOR, TOKEN, transport='https'), tmp_path / '不降级', timeout=1)
    with pytest.raises(ProtocolError) as failure: client.identity()
    thread.join(3)
    assert failure.value.code == 'REMOTE_UNAVAILABLE' and not thread.is_alive()
    assert len(received) == 1 and received[0][0] == 0x16 and b'Bearer ' not in received[0] and b'GET ' not in received[0]


def test_missing_public_ca_fails_closed_and_environment_ca_is_not_used(tmp_path, monkeypatch, certificates):
    import certifi
    monkeypatch.setenv('SSL_CERT_FILE', str(certificates / 'ca.pem'))
    monkeypatch.setenv('SSL_CERT_DIR', str(certificates))
    context = client_module.create_tls_context()
    assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
    monkeypatch.setattr(certifi, 'where', lambda: str(tmp_path / '不存在公开CA'))
    with pytest.raises(ProtocolError) as failure: client_module.create_tls_context()
    assert failure.value.code == 'TLS_TRUST_UNAVAILABLE'


def test_nonobject_identity_is_bounded_protocol_error(tmp_path, monkeypatch):
    client = LoopbackClient(LoopbackTarget('http://127.0.0.1:1', EXECUTOR, TOKEN), tmp_path / '身份')
    monkeypatch.setattr(client, '_request', lambda *_args, **_kwargs: [])
    with pytest.raises(ProtocolError) as failure: client.identity()
    assert failure.value.code == 'INVALID_REMOTE_RESPONSE'


def test_existing_executor_root_cannot_switch_transport(tmp_path):
    for initial, changed in [('loopback_http', 'https'), ('https', 'loopback_http')]:
        directory = tmp_path / initial; directory.mkdir()
        original = Executor(directory, TOKEN, initial); executor_id = original.executor_id; original.close()
        with pytest.raises(ProtocolError) as failure: Executor(directory, TOKEN, changed)
        assert failure.value.code == 'TRANSPORT_MISMATCH'
        restored = Executor(directory, TOKEN, initial)
        try: assert restored.executor_id == executor_id
        finally: restored.close()


@pytest.mark.parametrize('case', ['missing_options', 'mode_conflict', 'unsafe_key', 'wrong_key', 'malformed_cert', 'loopback_bind'])
def test_cli_bad_tls_config_fails_before_listener_or_database(tmp_path, certificates, case):
    token = tmp_path / 'token'; token.write_text(TOKEN); token.chmod(0o600)
    key = tmp_path / 'key'; key.write_bytes((certificates / 'valid.key').read_bytes()); key.chmod(0o600)
    cert = tmp_path / 'cert'; cert.write_bytes((certificates / 'valid.pem').read_bytes())
    args = ['--https', '--bind', '127.0.0.1', '--cert-file', str(cert), '--key-file', str(key)]
    if case == 'missing_options': args = ['--https']
    elif case == 'mode_conflict': args += ['--loopback-contract-only']
    elif case == 'unsafe_key': key.chmod(0o644)
    elif case == 'wrong_key': key.write_bytes((certificates / 'wrong-host.key').read_bytes())
    elif case == 'malformed_cert': cert.write_text('不是证书')
    elif case == 'loopback_bind': args = ['--loopback-contract-only', '--bind', '0.0.0.0']
    result = subprocess.run([sys.executable, '-m', 'ailab_control.remote', '--data-dir', str(tmp_path / 'data'), '--token-file', str(token), *args],
        cwd=tmp_path, env={'PATH': '/usr/bin:/bin', 'PYTHONPATH': str(ROOT / 'services/control')}, capture_output=True, text=True, timeout=8)
    assert result.returncode == 2 and result.stdout == '' and TOKEN not in result.stderr
    assert not (tmp_path / 'data').exists()


@pytest.mark.parametrize('case', json.loads((Path(__file__).resolve().parents[1] / 'fixtures/execution-origin-cases.json').read_text())['cases'])
def test_origin_contract(case):
    if case['accepted']:
        assert canonical_origin(case['origin'], case['transport']) == case['canonical']
    else:
        with pytest.raises(ProtocolError): canonical_origin(case['origin'], case['transport'])


def test_legacy_executor_metadata_remains_loopback_and_cannot_upgrade(tmp_path):
    original = Executor(tmp_path, TOKEN)
    identity = original.executor_id
    original.close()
    with sqlite3.connect(tmp_path / 'executor.sqlite3') as db:
        db.execute("DELETE FROM metadata WHERE key='transport'")
    with pytest.raises(ProtocolError) as failure:
        Executor(tmp_path, TOKEN, 'https')
    assert failure.value.code == 'TRANSPORT_MISMATCH'
    restored = Executor(tmp_path, TOKEN)
    try:
        assert restored.executor_id == identity and restored.transport == 'loopback_http'
        assert restored.identity()['network_remote_ready'] is False
    finally:
        restored.close()
