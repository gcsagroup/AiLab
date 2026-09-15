"""人工文字修订的独立版本；不改生成配方、原产物或执行快照，不调用生成器。"""

import copy
import difflib
import hashlib
import html
from pathlib import Path
import tempfile

from .assets import copy_asset, regular_path, verify_manifest
from .storage import Fault, digest, identifier

SCHEMA = 'work-revision-v1'
MAX_CHARACTERS = 16000
MAX_BYTES = 64 * 1024
KINDS = {'text': 'text', 'audio': 'voice_script', 'video': 'subtitles'}
FILES = {'text': ('revised-text.txt', 'text/plain'), 'voice_script': ('voice-script.txt', 'text/plain'), 'subtitles': ('subtitles.vtt', 'text/vtt')}
PUBLIC_FIELDS = ('id', 'project_id', 'resource_type', 'name', 'schema_version', 'work_id', 'parent_revision_id', 'revision', 'content_kind', 'content', 'artifact_id', 'manifest_digest', 'source_attempt_id', 'source_artifact_id', 'source_artifact_sha256', 'source_snapshot_digest', 'source_recipe_digest', 'editor', 'generation_recipe_changed', 'media_content_changed', 'duration_ms', 'created_at')


def fail(message, code='WORK_REVISION_INVALID', status=422):
    raise Fault(code, message, status)


def checked_bytes(artifact, maximum):
    if type(artifact.get('size')) is not int or not 0 <= artifact['size'] <= maximum:
        fail('作品内容超过当前修订读取上限。', 'WORK_REVISION_TOO_LARGE', 413)
    with regular_path(artifact['storage_path']).open('rb') as stream:
        raw = stream.read(maximum + 1)
    if len(raw) != artifact['size'] or hashlib.sha256(raw).hexdigest() != artifact['sha256']:
        fail('作品或修订文件读取期间发生变化。', 'ARTIFACT_CORRUPT', 409)
    return raw


def mp4_duration_ms(raw):
    """只接受封存普通 MP4 中唯一 mvhd 的明确时长；未知、重复或碎片时长拒绝。"""
    def boxes(data):
        cursor = 0
        while cursor < len(data):
            if cursor + 8 > len(data):
                raise ValueError('数据块头不完整')
            length, name = int.from_bytes(data[cursor:cursor + 4], 'big'), data[cursor + 4:cursor + 8]
            header = 8
            if length == 1:
                if cursor + 16 > len(data):
                    raise ValueError('扩展头不完整')
                length, header = int.from_bytes(data[cursor + 8:cursor + 16], 'big'), 16
            elif length == 0:
                length = len(data) - cursor
            if length < header or cursor + length > len(data):
                raise ValueError('数据块边界无效')
            yield name, data[cursor + header:cursor + length]
            cursor += length

    try:
        top = list(boxes(raw))
        moov = [body for name, body in top if name == b'moov']
        if len(moov) != 1 or any(name == b'moof' for name, _ in top):
            raise ValueError('缺少唯一普通影片索引')
        children = list(boxes(moov[0]))
        headers = [body for name, body in children if name == b'mvhd']
        if len(headers) != 1 or any(name == b'mvex' for name, _ in children):
            raise ValueError('缺少明确完整时长')
        header = headers[0]
        if not header or header[0] not in (0, 1):
            raise ValueError('不支持的时长版本')
        offset, width = (12, 4) if header[0] == 0 else (20, 8)
        if len(header) != (100 if header[0] == 0 else 112) or header[1:4] != b'\0\0\0':
            raise ValueError('时长头被截断')
        timescale = int.from_bytes(header[offset:offset + 4], 'big')
        duration = int.from_bytes(header[offset + 4:offset + 4 + width], 'big')
        if timescale <= 0 or duration <= 0 or duration == (1 << (width * 8)) - 1:
            raise ValueError('时长未知')
        milliseconds = duration * 1000 // timescale
        if not 1 <= milliseconds <= 60 * 60 * 1000:
            raise ValueError('时长超出当前范围')
        return milliseconds
    except (ValueError, OverflowError) as error:
        raise Fault('SUBTITLE_DURATION_UNKNOWN', '源 MP4 没有可确认的完整时长，不能保存字幕时间。', 409) from error


def valid_text(value, allow_empty=False):
    if not isinstance(value, str) or len(value) > MAX_CHARACTERS or (not allow_empty and not value.strip()) or any(ord(char) < 32 and char not in '\n\t' for char in value):
        fail('文字须为有效内容，最多 16000 字符，且不能包含控制字符。')
    try:
        if len(value.encode('utf-8')) > MAX_BYTES:
            fail('文字超过 64 KiB。', 'WORK_REVISION_TOO_LARGE', 413)
    except UnicodeError as error:
        raise Fault('WORK_REVISION_INVALID', '文字不是有效 Unicode。', 422) from error
    return value


def validate_content(kind, content, duration_ms=None, original=False):
    if not isinstance(content, dict):
        fail('修订内容必须是对象。')
    if kind != 'subtitles':
        if set(content) != {'text'}:
            fail('文字修订只接受 text 字段。')
        return {'text': valid_text(content['text'], allow_empty=original)}
    if set(content) != {'cues'} or not isinstance(content['cues'], list) or len(content['cues']) > 200:
        fail('字幕只接受 cues 数组，最多 200 条。')
    previous_end, characters = 0, 0
    for cue in content['cues']:
        if not isinstance(cue, dict) or set(cue) != {'start_ms', 'end_ms', 'text'}:
            fail('每条字幕必须只包含 start_ms、end_ms 和 text。')
        start, end = cue['start_ms'], cue['end_ms']
        if type(start) is not int or type(end) is not int or not 0 <= previous_end <= start < end or type(duration_ms) is not int or end > duration_ms:
            fail('字幕时间必须是整数毫秒、按顺序不重叠，并在源视频实际时长内。')
        text = valid_text(cue['text'])
        if len(text) > 500 or len(text.splitlines()) > 3 or '\n\n' in text or '-->' in text:
            fail('每条字幕最多 500 字符和三行，不能嵌入字幕分隔符。')
        previous_end, characters = end, characters + len(text)
    if characters > MAX_CHARACTERS:
        fail('字幕总文字超过 16000 字符。')
    return copy.deepcopy(content)


def content_bytes(kind, content):
    if kind != 'subtitles':
        raw = content['text'].encode('utf-8')
    else:
        def timestamp(value):
            seconds, milliseconds = divmod(value, 1000)
            minutes, seconds = divmod(seconds, 60)
            hours, minutes = divmod(minutes, 60)
            return f'{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}'
        chunks = ['WEBVTT\n\n']
        for index, cue in enumerate(content['cues'], 1):
            chunks.append(f"{index}\n{timestamp(cue['start_ms'])} --> {timestamp(cue['end_ms'])}\n{html.escape(cue['text'], quote=False)}\n\n")
        raw = ''.join(chunks).encode('utf-8')
    if len(raw) > MAX_BYTES:
        fail('修订文件超过 64 KiB。', 'WORK_REVISION_TOO_LARGE', 413)
    return raw


class WorkRevisions:
    def __init__(self, service):
        self.service, self.store = service, service.store

    def original_source(self, work_id):
        with self.store.transaction():
            work = self.store.get('work', work_id)
            attempt = self.store.get('attempt', work['source_attempt'])
        snapshot = attempt.get('snapshot', {})
        if attempt['project_id'] != work['project_id'] or snapshot.get('operation') != 'generate' or attempt.get('compute_outcome') != 'succeeded' or attempt.get('collection_state') != 'succeeded' or work['recipe'] != snapshot or digest(snapshot) != attempt.get('snapshot_digest'):
            fail('作品原生成来源不完整或已变化，不能保存人工修订。', 'WORK_SOURCE_CHANGED', 409)
        modality = snapshot.get('kind', 'text')
        artifact = self.service.delivery.artifact_for_path(attempt, 'result.txt') if modality == 'text' else self.service.media.primary(attempt)
        if artifact['id'] != work['artifact_id'] or artifact['project_id'] != work['project_id']:
            fail('作品引用与封存原产物不一致。', 'WORK_SOURCE_CHANGED', 409)
        return {'work': work, 'attempt': attempt, 'artifact': artifact}

    def source(self, work_id):
        source = self.original_source(work_id)
        work, attempt, artifact = source['work'], source['attempt'], source['artifact']
        snapshot = attempt['snapshot']
        modality = snapshot.get('kind', 'text')
        if modality not in KINDS:
            fail('当前只提供文本、TTS 配音文案和视频外置字幕修订。', 'WORK_REVISION_UNSUPPORTED', 409)
        kind = KINDS[modality]
        duration_ms = None
        if modality == 'text':
            if artifact.get('media_type') != 'text/plain':
                fail('原作品不是文本正文。', 'WORK_SOURCE_CHANGED', 409)
            try:
                content = {'text': checked_bytes(artifact, MAX_BYTES).decode('utf-8')}
            except UnicodeError as error:
                raise Fault('ARTIFACT_CORRUPT', '原作品不是 UTF-8 文本。', 409) from error
            basis = 'generated_text'
        elif modality == 'audio':
            content, basis = {'text': snapshot.get('input', {}).get('prompt')}, 'generation_input'
        else:
            duration_ms = mp4_duration_ms(checked_bytes(artifact, 64 * 1024 * 1024))
            content, basis = {'cues': []}, 'no_original_subtitle_artifact'
        content = validate_content(kind, content, duration_ms, original=True)
        return {'work': work, 'attempt': attempt, 'artifact': artifact, 'content_kind': kind, 'original_content': content,
                'original_basis': basis, 'duration_ms': duration_ms}

    def verify_revision(self, source, revision_id):
        revision = self.store.get('work-revision', revision_id)
        work, attempt = source['work'], source['attempt']
        if revision.get('schema_version') != SCHEMA or revision.get('editor') != 'user_action' or revision.get('generation_recipe_changed') is not False or revision.get('media_content_changed') is not False:
            fail('修订版本类型、编辑来源或原媒体声明不符。', 'WORK_REVISION_SOURCE_MISMATCH', 409)
        if revision['work_id'] != work['id'] or revision['project_id'] != work['project_id'] or revision['content_kind'] != source['content_kind'] or revision['source_attempt_id'] != attempt['id'] or revision['source_artifact_id'] != source['artifact']['id'] or revision['source_artifact_sha256'] != source['artifact']['sha256'] or revision['source_recipe_digest'] != revision['source_snapshot_digest']:
            fail('修订来源与当前作品不符。', 'WORK_REVISION_SOURCE_MISMATCH', 409)
        try:
            self.service.checkpoints.verify_lineage(attempt, revision['source_snapshot_digest'])
        except (ValueError, TypeError, KeyError) as error:
            raise Fault('WORK_REVISION_SOURCE_MISMATCH', '修订原快照没有完整恢复来源。', 409) from error
        content = validate_content(source['content_kind'], revision['content'], source['duration_ms'])
        raw = content_bytes(source['content_kind'], content)
        artifact = self.store.get('artifact', revision['artifact_id'])
        filename, mime = FILES[source['content_kind']]
        manifest = [{'path': filename, 'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}]
        if revision['manifest'] != manifest or revision['manifest_digest'] != digest(manifest) or artifact.get('work_revision_id') != revision_id or artifact.get('origin') != 'user_action' or artifact['attempt_id'] is not None or artifact['project_id'] != work['project_id'] or artifact['relative_path'] != filename or artifact['media_type'] != mime or artifact['sha256'] != manifest[0]['sha256'] or artifact['size'] != len(raw):
            fail('人工修订文件身份不完整。', 'ARTIFACT_CORRUPT', 409)
        verify_manifest(regular_path(artifact['storage_path']).parent, manifest)
        if checked_bytes(artifact, MAX_BYTES) != raw:
            fail('修订记录与实际文件不符。', 'ARTIFACT_CORRUPT', 409)
        return revision, artifact

    def public_revision(self, revision):
        public = {name: revision[name] for name in PUBLIC_FIELDS}
        public['changes'] = {name: revision['changes'][name] for name in ('format', 'from_content_sha256', 'to_content_sha256', 'diff')}
        return public

    def view(self, work_id, limit=100, before_revision=None):
        if type(limit) is not int or not 1 <= limit <= 100:
            fail('每次最多读取 100 个修订版本。')
        if before_revision is not None and (type(before_revision) is not int or before_revision < 1):
            fail('历史修订游标必须是正整数。')
        source = self.source(work_id)
        work = source['work']
        revisions = [item for item in self.store.list('work-revision', work['project_id'])
                     if item['work_id'] == work_id and (before_revision is None or item['revision'] < before_revision)]
        revisions.sort(key=lambda item: item['revision'])
        if work.get('current_revision_id'):
            self.verify_revision(source, work['current_revision_id'])
        items = []
        for revision in revisions[-limit:]:
            verified, _ = self.verify_revision(source, revision['id'])
            items.append(self.public_revision(verified))
        return {'work_id': work_id, 'work_revision': work['revision'], 'current_revision_id': work.get('current_revision_id'),
                'content_kind': source['content_kind'], 'duration_ms': source['duration_ms'],
                'original': {'revision_id': None, 'artifact_id': source['artifact']['id'], 'sha256': source['artifact']['sha256'], 'content': source['original_content'], 'basis': source['original_basis']},
                'items': items, 'has_more': len(revisions) > limit, 'generation_recipe_unchanged': True,
                'next_before_revision': items[0]['revision'] if len(revisions) > limit else None,
                'media_policy': '人工修订只保存独立文字或外置字幕；原媒体没有重新合成、混音或烧录。'}

    def create(self, work_id, payload, key):
        scope = 'work-revision:' + work_id
        with self.store.transaction():
            if previous := self.store.replay(scope, key, payload):
                return previous
        if not isinstance(payload, dict) or set(payload) != {'expected_revision', 'parent_revision_id', 'content_kind', 'content'} or type(payload['expected_revision']) is not int or payload['expected_revision'] < 1 or payload['parent_revision_id'] is not None and not isinstance(payload['parent_revision_id'], str):
            fail('修订请求须包含当前作品版本、明确父版本、内容类型与内容。')
        source = self.source(work_id)
        work, attempt, original_artifact = source['work'], source['attempt'], source['artifact']
        if payload['content_kind'] != source['content_kind']:
            fail('修订类型与当前作品不符。', 'WORK_REVISION_UNSUPPORTED', 409)
        if work['revision'] != payload['expected_revision'] or work.get('current_revision_id') != payload['parent_revision_id']:
            fail('作品已有后续修订，请查看差异后重新保存；未重新挂接旧父版本。', 'REVISION_CONFLICT', 409)
        parent, parent_artifact = self.verify_revision(source, payload['parent_revision_id']) if payload['parent_revision_id'] else (None, None)
        before = parent['content'] if parent else source['original_content']
        content = validate_content(source['content_kind'], payload['content'], source['duration_ms'])
        if content == before:
            fail('修订与父版本内容相同，没有创建空版本。', 'WORK_REVISION_UNCHANGED', 409)
        raw, old_raw = content_bytes(source['content_kind'], content), content_bytes(source['content_kind'], before)
        filename, mime = FILES[source['content_kind']]
        manifest = [{'path': filename, 'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}]
        manifest_digest = digest(manifest)
        difference = []
        for line in difflib.unified_diff(old_raw.decode('utf-8').splitlines(keepends=True), raw.decode('utf-8').splitlines(keepends=True), fromfile='parent', tofile='revision'):
            difference.append(line if line.endswith('\n') else line + '\n\\ No newline at end of file\n')
        changes = {'format': 'unified-diff', 'from_content_sha256': hashlib.sha256(old_raw).hexdigest(), 'to_content_sha256': manifest[0]['sha256'], 'diff': ''.join(difference)}
        with tempfile.TemporaryDirectory(prefix='work-revision-', dir=self.service.root) as temporary:
            path = Path(temporary) / filename
            path.write_bytes(raw)
            destination = copy_asset(path, self.service.root / 'assets', manifest, manifest_digest)
        with self.store.transaction():
            if previous := self.store.replay(scope, key, payload):
                return previous
            if self.store.get('work', work_id) != work or self.store.get('attempt', attempt['id']) != attempt or self.store.get('artifact', original_artifact['id']) != original_artifact or parent and (self.store.get('work-revision', parent['id']) != parent or self.store.get('artifact', parent_artifact['id']) != parent_artifact):
                fail('保存期间作品或来源已变化，没有覆盖其他修订。', 'REVISION_CONFLICT', 409)
            revision_id = identifier('work-revision')
            artifact = self.service.resource('artifact', work['project_id'], name=filename, relative_path=filename, storage_path=str(destination / filename),
                                             size=len(raw), sha256=manifest[0]['sha256'], media_type=mime, attempt_id=None, origin='user_action', work_revision_id=revision_id)
            revision = self.service.resource('work-revision', work['project_id'], name='人工修订 ' + str(work['revision'] + 1), schema_version=SCHEMA,
                                            work_id=work_id, parent_revision_id=payload['parent_revision_id'], revision=work['revision'] + 1,
                                            content_kind=source['content_kind'], content=content, artifact_id=artifact['id'], manifest=manifest, manifest_digest=manifest_digest,
                                            source_attempt_id=attempt['id'], source_artifact_id=original_artifact['id'], source_artifact_sha256=original_artifact['sha256'],
                                            source_snapshot_digest=attempt['snapshot_digest'], source_recipe_digest=digest(work['recipe']), editor='user_action', changes=changes,
                                            generation_recipe_changed=False, media_content_changed=False, duration_ms=source['duration_ms'])
            revision['id'] = revision_id
            work.update(revision=revision['revision'], current_revision_id=revision_id)
            self.store.put('artifact', artifact)
            self.store.put('work-revision', revision)
            self.store.put('work', work)
            response = {'work': self.service.public(work), 'revision': self.public_revision(revision), 'generation_recipe_unchanged': True, 'media_content_changed': False}
            self.store.remember(scope, key, payload, response)
            return response

    def generation_recipe(self, work_id):
        return copy.deepcopy(self.original_source(work_id)['work']['recipe'])

    def export_selection(self, work_id, revision_id, project_id):
        """供正式导出器挂载；null 选原版，固定 revision ID 选修订，不跟随当前指针。"""
        source = self.source(work_id) if revision_id is not None else self.original_source(work_id)
        work, original = source['work'], source['artifact']
        if work['project_id'] != project_id:
            fail('作品属于其他项目。', 'PROJECT_MISMATCH', 403)
        files = [{'path': 'work/' + original['name'], 'source': original['storage_path'], 'size': original['size'], 'sha256': original['sha256']}]
        revision = None
        if revision_id is not None:
            revision, artifact = self.verify_revision(source, revision_id)
            files.append({'path': 'revision/' + artifact['name'], 'source': artifact['storage_path'], 'size': artifact['size'], 'sha256': artifact['sha256']})
        version_id = revision_id or original['id']
        metadata = {'id': work_id, 'name': work['name'], 'source_attempt': work['source_attempt'], 'artifact_id': original['id'],
                    'selected_version': {'type': 'revision' if revision else 'original', 'id': version_id, 'revision_id': revision_id},
                    'content_kind': source.get('content_kind', KINDS.get(source['attempt']['snapshot'].get('kind', 'text'))), 'original_basis': source.get('original_basis', 'sealed_original_artifact'), 'revision': self.public_revision(revision) if revision else None,
                    'generation_recipe_changed': False, 'media_content_changed': False,
                    'media_policy': '修订文字或字幕为独立文件，原媒体没有重新合成、混音或烧录。'}
        return {'work': {**work, 'version_id': version_id}, 'files': files, 'metadata': metadata, 'recipe': copy.deepcopy(work['recipe'])}
