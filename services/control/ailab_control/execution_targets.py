"""项目执行目标；凭据只驻留内存，持久引用由原生宿主提供。"""

import re
import threading

from .remote.client import LoopbackClient, LoopbackTarget
from .remote.protocol import ProtocolError
from .storage import Fault, now


class ExecutionTargets:
    def __init__(self, service):
        self.service = service
        self.store = service.store
        self.secrets = {}
        self.lock = threading.RLock()

    @staticmethod
    def validate(origin, executor_id, token, transport="loopback_http", validation_scope=None):
        if not isinstance(token, str) or not 32 <= len(token) <= 512 or any(ord(c) < 33 or ord(c) > 126 for c in token):
            raise Fault('INVALID_CREDENTIAL', '连接凭据须为 32 至 512 位可见英文字符。')
        try:
            return LoopbackTarget(origin, executor_id, token, validation_scope, transport)
        except (ValueError, ProtocolError) as error:
            raise Fault(getattr(error, 'code', 'INVALID_EXECUTION_TARGET'), getattr(error, 'message', '执行目标地址无效。'), getattr(error, 'status', 400)) from None

    @staticmethod
    def reference(value):
        if not isinstance(value, str) or not re.fullmatch(r'remote-credential-[0-9a-f]{32}', value):
            raise Fault('INVALID_CREDENTIAL_REFERENCE', '系统凭据引用格式无效。')
        return value

    def public(self, value):
        with self.lock:
            available = value['id'] in self.secrets
        return {**self.service.public(value), 'credential_status': 'available' if available else 'required',
                'credential_storage': 'keychain' if value.get('credential_ref') else 'session' if available else 'none',
                'credential_cleanup_refs': list(value.get('credential_cleanup_refs', [])),
                'credential_cleanup_required': bool(value.get('credential_cleanup_refs'))}

    def get(self, target_id):
        return self.public(self.store.get('execution-target', target_id))

    def listing(self, project_id):
        return {'items': [self.public(value) for value in self.store.list('execution-target', project_id)]}

    def create(self, payload, key, host=False):
        target = self.validate(payload['origin'], payload['executor_id'], payload['credential_token'], payload.get('transport', 'loopback_http'))
        reference = self.reference(payload['credential_ref']) if host else None
        # Store 仅保存整份请求的摘要，不保存原始凭据。
        request = payload
        with self.store.transaction():
            if previous := self.store.replay('execution-target:create', key, request):
                return self.get(previous['id'])
            self.store.get('project', payload['project_id'])
            value = self.service.resource('execution-target', payload['project_id'], name=payload['name'],
                                          origin=target.origin, executor_id=payload['executor_id'], transport=target.transport,
                                          credential_ref=reference, credential_cleanup_refs=[], revision=1, validation_scope=target.validation_scope,
                                          connection_state='unchecked', checked_at=None, protocol_ready=False,
                                          network_remote_ready=False, nvidia_ready=False, adapters={})
            self.store.put('execution-target', value)
            self.store.remember('execution-target:create', key, request, {'id': value['id']})
            with self.lock:
                self.secrets[value['id']] = payload['credential_token']
        return self.public(value)

    def credentials(self, target_id, payload, host=False, forget=False, key=None):
        with self.store.transaction():
            scope = f'execution-target:{target_id}:credentials:{"forget" if forget else "set"}'
            if host and (previous := self.store.replay(scope, key, payload)):
                return self.get(previous['id'])
            value = self.store.get('execution-target', target_id)
            if value['revision'] != payload['expected_revision']:
                raise Fault('REVISION_CONFLICT', '执行目标已更新，请刷新后再连接。', 409, current_revision=value['revision'])
            pending = list(value.get('credential_cleanup_refs', []))
            if not host and (value.get('credential_ref') or pending):
                raise Fault('HOST_AUTH_REQUIRED', '此目标的系统凭据只能通过原生连接操作管理。', 403)
            if not forget:
                self.validate(value['origin'], value['executor_id'], payload['credential_token'], value.get('transport', 'loopback_http'), value['validation_scope'])
                reference = self.reference(payload['credential_ref']) if host else None
            else:
                reference = None
            if reference in pending:
                raise Fault('CREDENTIAL_REVOKED', '已撤销的凭据引用不能重新启用，请重新输入。', 409)
            old_reference = value.get('credential_ref')
            if old_reference and old_reference != reference and old_reference not in pending:
                pending.append(self.reference(old_reference))
            # 保留一个槽位，使撤销当前凭据始终可以先断开，再重试钥匙串清理。
            if len(pending) > 16 or (not forget and len(pending) >= 16):
                raise Fault('CREDENTIAL_CLEANUP_REQUIRED', '请先清除尚未移除的系统凭据，再更新连接。', 409)
            value.update(credential_ref=reference, credential_cleanup_refs=pending,
                         revision=value['revision'] + 1, connection_state='unchecked',
                         checked_at=None, protocol_ready=False, network_remote_ready=False, nvidia_ready=False,
                         nvidia_environment=None, adapters={}, last_error=None)
            self.store.put('execution-target', value)
            if host:
                self.store.remember(scope, key, payload, {'id': target_id})
            with self.lock:
                if forget:
                    self.secrets.pop(target_id, None)
                else:
                    self.secrets[target_id] = payload['credential_token']
        return self.public(value)

    def cleanup_credentials(self, target_id, payload, key):
        reference = self.reference(payload['credential_ref'])
        with self.store.transaction():
            scope = f'execution-target:{target_id}:credentials:cleanup'
            if previous := self.store.replay(scope, key, payload):
                return self.get(previous['id'])
            value = self.store.get('execution-target', target_id)
            if value['revision'] != payload['expected_revision']:
                raise Fault('REVISION_CONFLICT', '执行目标已更新，请刷新后再清理。', 409, current_revision=value['revision'])
            pending = list(value.get('credential_cleanup_refs', []))
            if reference not in pending or reference == value.get('credential_ref'):
                raise Fault('CREDENTIAL_CLEANUP_MISMATCH', '此引用不属于该目标待清理的凭据。', 409)
            pending.remove(reference)
            value.update(credential_cleanup_refs=pending, revision=value['revision'] + 1)
            self.store.put('execution-target', value)
            self.store.remember(scope, key, payload, {'id': target_id})
        return self.public(value)

    def client(self, target_id, project_id=None):
        value = self.store.get('execution-target', target_id)
        if project_id is not None and value['project_id'] != project_id:
            raise Fault('PROJECT_MISMATCH', '执行目标不属于当前项目。', 403)
        with self.lock:
            token = self.secrets.get(target_id)
        if token is None:
            raise Fault('CREDENTIAL_REQUIRED', '请通过设备与环境重新连接此执行目标。', 409)
        target = self.validate(value['origin'], value['executor_id'], token, value.get('transport', 'loopback_http'), value['validation_scope'])
        return LoopbackClient(target, self.service.root / 'remote-connections' / target_id), value

    def check(self, target_id):
        original = self.store.get('execution-target', target_id)
        client = None
        identity, failure, probe = None, None, None
        try:
            client, original = self.client(target_id)
            identity = client.identity()
            if identity.get('adapters', {}).get('nvidia-text', {}).get('installed'):
                client.timeout = 35
                probe = client.nvidia_probe()
        except ProtocolError as error:
            failure = {'code': error.code, 'message': error.message}
        with self.store.transaction():
            value = self.store.get('execution-target', target_id)
            if value['revision'] != original['revision']:
                raise Fault('REVISION_CONFLICT', '检查期间连接凭据已更新，请重新检查。', 409)
            value.update(checked_at=now(), connection_state='connected' if identity else 'disconnected',
                         network_remote_ready=bool(identity and client.target.transport == 'https'),
                         protocol_ready=identity is not None, nvidia_ready=bool(probe and probe.get('ready')),
                         adapters=identity.get('adapters', {}) if identity else {}, nvidia_environment=probe, last_error=failure)
            self.store.put('execution-target', value)
        return {**self.public(value), 'identity': identity}
