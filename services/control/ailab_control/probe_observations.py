"""本次控制服务会话的有界探测记录；不进入环境身份或运行快照。"""

from collections import deque
from contextlib import contextmanager
import copy
import json
import math
import os
import subprocess
import threading
import time

from .storage import now

ERROR_MESSAGES = {
    'PROBE_EXIT_NONZERO': '环境探测进程异常退出，请检查已选择的运行环境。',
    'PROBE_TIMEOUT': '环境探测超时，请检查运行环境后重新检测。',
    'PROBE_START_FAILED': '环境探测进程无法启动，请检查执行器及访问权限。',
    'PROBE_INVALID_JSON': '环境探测返回了无效输出，请检查执行器版本。',
    'PROBE_INVALID_FACTS': '环境探测返回的事实格式无效，请检查执行器版本。',
}

PROBE_STAGE_PREFIX = 'AILAB_PROBE_STAGE_V1 '
PROBE_STAGES = {'runtime_files', 'media_tools_files', 'dependency_versions', 'torch_import', 'engine_imports', 'tracker_start', 'tracker_reap'}


def _probe_stages(stderr):
    """只提取短行中的固定枚举与耗时；普通日志和未知字段一律丢弃。"""
    if isinstance(stderr, bytes):
        stderr = stderr.decode('utf-8', errors='replace')
    if not isinstance(stderr, str):
        return []
    stages, seen = [], set()
    for line in stderr.splitlines():
        if not line.startswith(PROBE_STAGE_PREFIX) or len(line) > 256:
            continue
        try:
            value = json.loads(line[len(PROBE_STAGE_PREFIX):])
        except ValueError:
            continue
        if not isinstance(value, dict) or set(value) != {'stage', 'status', 'elapsed_seconds'}:
            continue
        stage, status, elapsed = value['stage'], value['status'], value['elapsed_seconds']
        if not isinstance(stage, str) or stage not in PROBE_STAGES or stage in seen:
            continue
        if status not in ('succeeded', 'failed') or type(elapsed) not in (int, float) or not math.isfinite(elapsed) or elapsed < 0:
            continue
        stages.append({'stage': stage, 'status': status, 'elapsed_seconds': round(elapsed, 6)})
        seen.add(stage)
        if len(stages) == len(PROBE_STAGES):
            break
    return stages


class ProbeFailure(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(ERROR_MESSAGES[code])


class ProbeObservations:
    def __init__(self):
        self._records = deque(maxlen=32)
        self._total = 0
        self._environments = deque(maxlen=64)
        self._environment_total = 0
        self._lock = threading.Lock()

    def snapshot(self):
        with self._lock:
            return copy.deepcopy(list(self._records)), self._total - len(self._records)

    def environment_snapshot(self):
        with self._lock:
            return copy.deepcopy(list(self._environments)), self._environment_total - len(self._environments)

    @contextmanager
    def environment(self, engine, kind, origin, refresh):
        """记录一次环境调用；纳秒仅能在同一控制进程内比较，不是跨进程统一时钟。"""
        if engine not in {'mlx', 'diffusers', 'kokoro'} or kind not in {'text', 'image', 'video', 'audio'} or origin not in {'environment', 'capabilities', 'devices'}:
            raise ValueError('环境调用类型不受支持。')
        record = {'engine': engine, 'kind': kind, 'origin': origin, 'refresh': bool(refresh), 'control_pid': os.getpid(),
                  'started_monotonic_ns': time.monotonic_ns(), 'lock_acquired_monotonic_ns': None,
                  'identity_started_monotonic_ns': None, 'identity_completed_monotonic_ns': None,
                  'completed_monotonic_ns': None, 'cache_outcome': 'not_checked', 'status': 'failed',
                  'ready': None, 'completed_at': None}
        try:
            yield record
            record['status'] = 'completed'
        finally:
            record['completed_monotonic_ns'] = time.monotonic_ns()
            record['completed_at'] = now()
            with self._lock:
                self._environments.append(record)
                self._environment_total += 1

    @contextmanager
    def identity(self, record):
        record['identity_started_monotonic_ns'] = time.monotonic_ns()
        try:
            yield
        finally:
            record['identity_completed_monotonic_ns'] = time.monotonic_ns()

    def run(self, engine, backend, command, *, timeout, env, is_ready):
        if engine not in {'mlx', 'diffusers', 'kokoro'} or backend not in {'bundled', 'external_python'}:
            raise ValueError('环境探测类型不受支持。')
        started = time.monotonic_ns()
        error_code, returncode = 'PROBE_INCOMPLETE', None
        stages = []
        has_stages = backend == 'bundled' and engine in {'diffusers', 'kokoro'}
        try:
            try:
                probe = subprocess.run(command, capture_output=True, text=True, timeout=timeout, env=env)
            except subprocess.TimeoutExpired as error:
                if has_stages:
                    stages = _probe_stages(error.stderr)
                raise ProbeFailure('PROBE_TIMEOUT') from None
            except OSError:
                raise ProbeFailure('PROBE_START_FAILED') from None
            except UnicodeError:
                raise ProbeFailure('PROBE_INVALID_JSON') from None
            returncode = probe.returncode
            if has_stages:
                stages = _probe_stages(probe.stderr)
            if returncode != 0:
                raise ProbeFailure('PROBE_EXIT_NONZERO')
            try:
                facts = json.loads(probe.stdout)
            except ValueError:
                raise ProbeFailure('PROBE_INVALID_JSON') from None
            if isinstance(facts, dict):
                # 耗时只属于会话诊断，不能进入 versions、环境摘要或任务快照。
                facts.pop('probe_stages', None)
            device_field = 'metal' if engine == 'mlx' else 'device_ready'
            if not isinstance(facts, dict) or type(facts.get(device_field)) is not bool or not isinstance(facts.get('dependencies'), dict):
                raise ProbeFailure('PROBE_INVALID_FACTS')
            try:
                ready = bool(is_ready(facts))
            except (ValueError, TypeError, KeyError):
                raise ProbeFailure('PROBE_INVALID_FACTS') from None
            error_code = None if ready else 'PROBE_NOT_READY'
            return facts, ready
        except ProbeFailure as error:
            error_code = error.code
            raise
        finally:
            completed = time.monotonic_ns()
            elapsed = (completed - started) / 1_000_000_000
            record = {'engine': engine, 'execution_backend': backend, 'status': 'failed' if error_code else 'succeeded',
                      'error_code': error_code, 'elapsed_seconds': round(max(0, elapsed), 6) if math.isfinite(elapsed) else None,
                      'control_pid': os.getpid(), 'started_monotonic_ns': started, 'completed_monotonic_ns': completed,
                      'returncode': returncode if type(returncode) is int else None, 'completed_at': now()}
            if stages:
                record['stages'] = stages
            with self._lock:
                self._records.append(record)
                self._total += 1
