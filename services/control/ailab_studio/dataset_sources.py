"""Read-only Hugging Face and Kaggle adapters; no remote dataset code is executed."""
import base64
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

ORIGINS = {'huggingface': 'https://huggingface.co', 'kaggle': 'https://www.kaggle.com'}


class RangeUnavailable(ValueError):
    pass


def repository(value):
    if not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]{0,95}/[A-Za-z0-9_][A-Za-z0-9_.-]{0,95}', value):
        raise ValueError('数据集 ID 应为 owner/name')
    return value


def relative(value):
    if not value or len(value) > 500 or '\\' in value or ':' in value or any(x in ('', '.', '..') for x in value.split('/')):
        raise ValueError('数据文件路径无效')
    if any(ord(c) < 32 for c in value): raise ValueError('数据文件路径无效')
    return value


def trusted_url(url):
    parsed = urllib.parse.urlsplit(url)
    host = parsed.hostname or ''
    allowed = ('huggingface.co', 'hf.co', 'kaggle.com', 'kaggleusercontent.com', 'googleusercontent.com', 'storage.googleapis.com', 'amazonaws.com')
    if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port not in (None, 443) or not any(host == x or host.endswith('.' + x) for x in allowed):
        raise ValueError('数据来源返回了未支持的下载地址')


class Redirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        trusted_url(newurl)
        redirect = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirect and urllib.parse.urlsplit(req.full_url).netloc != urllib.parse.urlsplit(newurl).netloc:
            redirect.remove_header('Authorization')
        return redirect


class Sources:
    def __init__(self):
        self.secrets = {}
        self.opener = urllib.request.build_opener(Redirects())

    def configure(self, provider, token, username=''):
        if provider not in ORIGINS: raise ValueError('数据来源不支持')
        if any(c in token + username for c in ('\r', '\n', '\x00')): raise ValueError('凭据不能包含换行或空字符')
        self.secrets[provider] = (token.strip(), username.strip())
        return self.status()

    def headers(self, provider):
        value, username = self.secrets.get(provider, (None, ''))
        if value is None:
            value = os.environ.get('HF_TOKEN', '') if provider == 'huggingface' else os.environ.get('KAGGLE_API_TOKEN', '')
            if provider == 'kaggle' and not value:
                value, username = os.environ.get('KAGGLE_KEY', ''), os.environ.get('KAGGLE_USERNAME', '')
        result = {'User-Agent': 'AiLab-Studio-Dataset-Market/1', 'Accept-Encoding': 'identity'}
        if value and any(ord(c) < 33 or ord(c) > 126 for c in value):
            raise ValueError('访问凭据格式无效，请重新配置 Token / Key')
        if value:
            result['Authorization'] = 'Basic ' + base64.b64encode(f'{username}:{value}'.encode()).decode() if username else 'Bearer ' + value
        return result

    def status(self):
        return {'items': [{'id': p, 'name': 'Hugging Face' if p == 'huggingface' else 'Kaggle', 'credential_configured': 'Authorization' in self.headers(p)} for p in ORIGINS]}

    def open(self, provider, url, extra=None):
        trusted_url(url)
        # Credentials are only sent to the provider API, never to signed CDN URLs.
        headers = self.headers(provider) if urllib.parse.urlsplit(url).netloc == urllib.parse.urlsplit(ORIGINS[provider]).netloc else {'Accept-Encoding': 'identity'}
        try:
            return self.opener.open(urllib.request.Request(url, headers={**headers, **(extra or {})}), timeout=15)
        except urllib.error.HTTPError as exc:
            if exc.code == 416: raise RangeUnavailable('来源不能继续此范围，将重新下载当前文件') from None
            if exc.code in (401, 403): raise ValueError('来源拒绝访问，请配置凭据并在来源网站确认数据访问权限') from None
            if exc.code == 404: raise ValueError('来源未找到该数据集、版本或文件') from None
            if exc.code == 429: raise ValueError('来源请求过于频繁，请稍后重试') from None
            raise ValueError(f'数据来源请求失败（HTTP {exc.code}）') from None
        except (urllib.error.URLError, OSError, TimeoutError):
            raise ValueError('无法连接数据来源，请检查网络后重试') from None

    def json(self, provider, path, query=None):
        url = ORIGINS[provider] + path + ('?' + urllib.parse.urlencode(query) if query else '')
        with self.open(provider, url) as response:
            body = response.read(8 * 1024 * 1024 + 1)
        if len(body) > 8 * 1024 * 1024: raise ValueError('来源元数据过大，请选择更小的数据集')
        try: return json.loads(body)
        except (ValueError, UnicodeError): raise ValueError('来源返回的元数据不是有效 JSON') from None

    def search(self, provider, query, page):
        if provider == 'huggingface':
            rows = self.json(provider, '/api/datasets', {'search': query, 'limit': min(100, page * 20 + 1), 'sort': 'downloads', 'direction': -1, 'full': 'true'})
            more = len(rows) > page * 20
            rows = rows[(page - 1) * 20:page * 20]
            items = [{'id': x['id'], 'title': x['id'], 'description': x.get('description', '')[:400], 'downloads': x.get('downloads'), 'license': (x.get('cardData') or {}).get('license')} for x in rows]
        elif provider == 'kaggle':
            rows = self.json(provider, '/api/v1/datasets/list', {'search': query, 'page': page, 'pageSize': 20})
            if not isinstance(rows, list): raise ValueError('Kaggle 搜索结果格式不支持')
            items = [{'id': x['ref'], 'title': x.get('title', x['ref']), 'description': x.get('subtitle', ''), 'downloads': x.get('downloadCount'), 'license': x.get('licenseName')} for x in rows]
        else: raise ValueError('数据来源不支持')
        return {'items': items, 'page': page, 'has_more': page < 5 and (more if provider == 'huggingface' else len(items) == 20)}

    def detail(self, provider, dataset, revision=''):
        repository(dataset)
        escaped = urllib.parse.quote(dataset, safe='/')
        if provider == 'huggingface':
            if len(revision) > 150 or any(ord(c) < 32 for c in revision): raise ValueError('版本标识无效')
            suffix = '/revision/' + urllib.parse.quote(revision, safe='') if revision else ''
            info = self.json(provider, '/api/datasets/' + escaped + suffix, {'blobs': 'true'})
            sha = info.get('sha', '')
            if not re.fullmatch(r'[a-f0-9]{40}', sha): raise ValueError('来源未提供固定提交版本')
            files = []
            for file in info.get('siblings', []):
                path = relative(file['rfilename']); lfs = file.get('lfs') or {}
                files.append({'path': path, 'size': file.get('size', lfs.get('size')), 'expected_sha256': lfs.get('sha256')})
            versions = [revision or 'main']
            try:
                refs = self.json(provider, '/api/datasets/' + escaped + '/refs')
                versions += [r['name'] for r in refs.get('branches', []) + refs.get('tags', [])]
            except ValueError: pass  # The resolved immutable SHA remains usable.
            card = info.get('cardData') or {}
            description = info.get('description', '')
            if any(f['path'] == 'README.md' for f in files):
                try:
                    with self.open(provider, f'{ORIGINS[provider]}/datasets/{escaped}/resolve/{sha}/README.md') as response:
                        description = response.read(65536).decode('utf-8', errors='replace')
                except ValueError as exc:
                    description = (description or '') + '\n\nREADME 未读取：' + str(exc)
            return {'provider': provider, 'dataset': dataset, 'title': dataset, 'revision': sha, 'requested_revision': revision or 'main',
                    'versions': list(dict.fromkeys([*versions, sha])), 'description': description[:65536], 'license': card.get('license'),
                    'source_url': ORIGINS[provider] + '/datasets/' + escaped, 'files': files, 'gated': bool(info.get('gated'))}
        if provider != 'kaggle': raise ValueError('数据来源不支持')
        if revision and not re.fullmatch(r'[1-9][0-9]{0,8}', revision): raise ValueError('Kaggle 版本必须为正整数')
        info = self.json(provider, '/api/v1/datasets/view/' + escaped, {'datasetVersionNumber': revision} if revision else None)
        version = str(revision or info.get('currentVersionNumber') or info.get('versionNumber') or '')
        if not re.fullmatch(r'[1-9][0-9]*', version): raise ValueError('Kaggle 未返回有效版本号')
        versions = [str(v.get('versionNumber')) for v in info.get('versions', []) if v.get('versionNumber')]
        # Kaggle transfers a versioned archive, not a collection of HF file URLs.
        return {'provider': provider, 'dataset': dataset, 'title': info.get('title', dataset), 'revision': version, 'requested_revision': version,
                'versions': list(dict.fromkeys([version, *versions])), 'description': info.get('description', '')[:65536],
                'license': info.get('licenseName') or info.get('licenses'), 'source_url': ORIGINS[provider] + '/datasets/' + escaped,
                'files': [{'path': 'dataset.zip', 'size': None, 'expected_sha256': None}], 'gated': False,
                'archive_note': '按指定版本下载 ZIP；完成后手动解压并导入所需数据文件。'}

    def file_url(self, selection, path):
        dataset = urllib.parse.quote(selection['dataset'], safe='/')
        version = urllib.parse.quote(selection['revision'], safe='')
        if selection['provider'] == 'huggingface':
            return f'https://huggingface.co/datasets/{dataset}/resolve/{version}/' + urllib.parse.quote(relative(path), safe='/')
        return f'https://www.kaggle.com/api/v1/datasets/download/{dataset}?datasetVersionNumber={version}'
