"""Durable, cancellable process jobs; one compute lease per local node."""
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
import psutil
from .storage import Store, uid
from .catalog import hardware, local_path, model_info, scan
from .runtimes import Runtimes, interpreter
from .ablation import compose
from .scheduler import Scheduler
from .materials import Materials
from .llm import ResidentLLM

TERMINAL = {'succeeded', 'failed', 'cancelled', 'interrupted'}
WORKERS = Path(__file__).resolve().parent / 'workers'


def process_alive(job):
    try:
        return abs(psutil.Process(job['pid']).create_time() - job['pid_started']) < 0.01
    except (KeyError, psutil.Error):
        return False


class Studio(Scheduler):
    def __init__(self, root, environment=None):
        self.store = Store(root); self.root = self.store.root
        self.default_environment = Path(environment).resolve() if environment else self.root / 'environment'
        try: saved_environment = self.store.get('settings', 'environment')['path']
        except (ValueError, KeyError): saved_environment = None
        self.environment = Path(saved_environment) if saved_environment else self.default_environment
        self.environment.mkdir(parents=True, exist_ok=True)
        for name in ('models', 'datasets'): (self.environment / name).mkdir(exist_ok=True)
        self.hardware = hardware()
        self.mutex = threading.RLock(); self.threads = set(); self.stopping = False
        self.runtimes = Runtimes(self)
        self.materials = Materials(self)
        self.llm = ResidentLLM(self)
        for job in self.store.list('job', 100000):
            if job['state'] not in TERMINAL and job['state'] != 'queued' and not (job['state'] == 'paused' and not job.get('pid')):
                job.update(state='interrupted', error='控制服务曾中断；未自动重新执行。', finished_at=time.time())
                self.store.put('job', job)
        self.start_scheduler()

    def paths(self):
        try: value = self.store.get('settings', 'paths')
        except ValueError: value = {}
        return {'id': 'paths', **{key: value.get(key) or str(self.environment / key) for key in ('models', 'datasets')}}

    def save_environment(self, raw):
        path = Path(raw).expanduser() if raw.strip() else self.default_environment
        if not path.is_absolute(): raise ValueError('环境安装目录必须是绝对路径')
        path = path.resolve()
        with self.mutex:
            if path == self.environment: return {'environment_dir': str(path)}
            if any(j['state'] not in TERMINAL for j in self.store.list('job', 1000000)):
                raise ValueError('请先完成或取消队列中的任务，再修改环境目录')
            if self.llm.status()['phase'] != 'unloaded': raise ValueError('请先卸载已加载的模型，再修改环境目录')
            path.mkdir(parents=True, exist_ok=True)
            # Test writability before changing persistent settings or runtime resolution.
            probe = path / ('.ailab-write-' + uid())
            with probe.open('x') as handle: handle.write('')
            probe.unlink()
            (path / 'runtimes').mkdir(exist_ok=True)
            for name in ('models', 'datasets'): (path / name).mkdir(exist_ok=True)
            old_paths = self.paths()
            self.store.put('settings', old_paths)
            self.store.put('settings', {'id':'environment', 'path':str(path)})
            self.environment = path
            self.runtimes.root = path / 'runtimes'
        return {'environment_dir': str(path)}

    def save_paths(self, value):
        for raw in value.values():
            if raw and not local_path(raw).is_dir(): raise ValueError('请选择文件夹')
        self.store.put('settings', {'id': 'paths', **value})
        return self.paths()

    def assets(self):
        paths = self.paths(); result = {}
        for kind in ('models', 'datasets'):
            try: result[kind] = scan(paths[kind], kind) if paths[kind] else []
            except (OSError, ValueError) as exc: result[kind] = []; result[kind + '_error'] = str(exc)
        return result

    def submit(self, kind, payload):
        config = payload.model_dump()
        split_media = kind == 'inference' and config.get('media_format') == 'comfyui' and config['workflow'] != 'chat'
        if split_media:
            for name in ('model', 'text_encoder', 'text_encoder_2', 'vae', 'clip_vision'):
                if not config.get(name): continue
                path = local_path(config[name])
                if not path.is_file() or path.suffix.lower() != '.safetensors': raise ValueError('分离组件需要本地 Safetensors 文件：' + name)
                config[name] = str(path)
            model = {'path': config['model'], 'format': 'comfyui'}
        else:
            model = model_info(config['model'])
        config['model'] = model['path']
        if kind in ('sft', 'ablation') and model['format'] != 'safetensors':
            raise ValueError('训练和消融需要完整 Safetensors LLM 模型目录')
        if kind == 'sft':
            quantization = json.loads((Path(config['model']) / 'config.json').read_text(encoding='utf-8')).get('quantization_config') or {}
            config['base_quantization'] = quantization
            if quantization:
                if config['method'] != 'lora': raise ValueError('量化基座目前支持 LoRA 微调，请选择 LoRA')
                quant_method = quantization.get('quant_method')
                if quant_method not in ('compressed-tensors', 'bitsandbytes'):
                    raise ValueError(f'当前训练适配支持 compressed-tensors（含 NVFP4）和 bitsandbytes，暂不支持 {quant_method}')
                config['weight_loading'] = 'dequantize' if quant_method == 'compressed-tensors' else 'quantized_lora'
            else: config['weight_loading'] = 'original'
            config['dataset'] = str(local_path(config['dataset']))
            runtime = 'training'
        elif kind == 'ablation':
            import tomllib
            preview = tomllib.loads(compose(config['toml'], config['fields'], config['model'], self.root / 'jobs' / 'validation'))
            runtime = 'vllm' if preview['model']['backend'] == 'vllm' else 'ablation'
        else:
            runtime = 'comfyui' if split_media else config['engine']
            if config.get('conversation_id'):
                conversation = self.store.get('conversation', config['conversation_id'])
                if config['workflow'] != 'chat' or conversation['messages'] != config['messages']:
                    raise ValueError('会话上下文已变化，请重新提交')
            expected = {'llama': 'gguf', 'vllm': 'safetensors', 'diffusers': 'diffusers', 'comfyui': 'comfyui'}[runtime]
            if model['format'] != expected: raise ValueError(f'{runtime} 需要 {expected} 格式')
            if config.get('mmproj'): config['mmproj'] = str(local_path(config['mmproj']))
            if runtime == 'llama' and any(m.get('image') for m in config['messages']) and (not config['mmproj'] or config['vision_handler'] == 'none'):
                raise ValueError('llama 视觉对话需要匹配的 mmproj 文件和视觉处理器')
            for message in config['messages']:
                if runtime == 'vllm' and message.get('image') and not model.get('vision'):
                    raise ValueError('所选模型未声明视觉能力，请选择视觉模型或移除含图片的上下文')
                if message.get('image'): decode_image(message['image'])
            if config.get('image'): decode_image(config['image'])
            if config.get('material_id'):
                material = self.materials.get(config['material_id'])
                if material['kind'] != 'image': raise ValueError('参考素材必须为图像')
                config['image_path'] = material['path']
        resolved = self.runtimes.resolve(runtime)
        config['runtime_path'] = resolved['path']; config['runtime_version'] = resolved['version']
        if kind == 'ablation':
            # Validate before reserving resources; final output paths are bound to the job later.
            compose(config['toml'], config['fields'], config['model'], self.root / 'jobs' / 'validation')
        return self.launch(kind, config, runtime)

    def _execute(self, key, target):
        try:
            with self.mutex:
                job = self.store.get('job', key)
                if job['state'] == 'cancelling': raise InterruptedError('已取消')
            self.checkpoint_pause(key)
            result = target(job, lambda command, **kw: self.run(key, command, **kw))
            if job['kind'] == 'inference' and isinstance(result, dict) and result.get('file'):
                file = Path(result['file']).resolve()
                if not file.is_relative_to(Path(job['output_dir']).resolve()): raise ValueError('生成产物路径无效')
                parameters = {k: v for k, v in job['config'].items() if k not in ('image', 'image_path', 'messages', 'runtime_path')}
                material = self.materials.add(file, 'generated', parameters=parameters, job_id=key)
                result['material_id'] = material['id']
            with self.mutex:
                job = self.store.get('job', key)
                job['state'] = 'cancelled' if job['state'] == 'cancelling' else 'succeeded'
                if job['state'] == 'succeeded' and job['config'].get('conversation_id') and isinstance(result, dict) and (result.get('text') or result.get('reasoning')):
                    try: conversation = self.store.get('conversation', job['config']['conversation_id'])
                    except ValueError: conversation = None
                    if conversation and conversation['messages'] == job['config']['messages']:
                        conversation['messages'].append({'role': 'assistant', 'content': result.get('text', ''), 'reasoning': result.get('reasoning'), 'image': None})
                        conversation['updated_at'] = time.time()
                        self.store.put('conversation', conversation)
                    else:
                        self.store.event(key, {'type': 'status', 'text': '会话上下文已修改，回答保留在任务结果中。'})
                job['result'] = result
                job['finished_at'] = time.time(); self.store.put('job', job)
        except Exception as exc:
            with self.mutex:
                job = self.store.get('job', key)
                job['state'] = 'cancelled' if job['state'] == 'cancelling' or isinstance(exc, InterruptedError) else 'failed'
                job.update(error=str(exc)[:2000], finished_at=time.time()); self.store.put('job', job)
                self.store.event(key, {'type': 'error', 'text': str(exc)[:2000]})
        finally:
            with self.mutex:
                self.threads.discard(threading.current_thread()); self.active.pop(key, None)
            self.wake.set()

    def run(self, key, command, env=None, collect=False):
        self.checkpoint_pause(key)
        env = dict(env or os.environ)
        env.update(AILAB_JOB_CONTROL_DIR=self.store.get('job', key)['output_dir'], HF_HOME=str(self.environment / 'huggingface'))
        env.update(PYTHONUNBUFFERED='1', PYTHONUTF8='1', TOKENIZERS_PARALLELISM='false', NO_COLOR='1')
        chunks = []
        with self.mutex:
            job = self.store.get('job', key)
            if job['state'] == 'cancelling' or self.stopping: raise InterruptedError('任务已取消')
            # Supervisor watches controller identity even when the controller crashes.
            supervisor = ['--studio-supervise'] if getattr(sys, 'frozen', False) else [str(WORKERS / 'supervisor.py')]
            wrapped = [sys.executable, *supervisor, str(os.getpid()), str(psutil.Process().create_time()), *command]
            process = subprocess.Popen(wrapped, cwd=job['output_dir'], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                       stdin=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                                       start_new_session=os.name != 'nt')
            job.update(pid=process.pid, pid_started=psutil.Process(process.pid).create_time())
            self.store.put('job', job)
        assert process.stdout
        for raw in iter(lambda: process.stdout.readline(65536), b''):
            line = raw.decode('utf-8', errors='replace').rstrip()
            line = re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', line)
            for name, secret in env.items():
                if len(secret) >= 8 and any(tag in name.upper() for tag in ('TOKEN', 'API_KEY', 'PASSWORD', 'SECRET')):
                    line = line.replace(secret, '[REDACTED]')
            event = {'type': 'log', 'text': line[:16000]}
            marker = line.rfind('@@AILAB ')
            if marker >= 0:
                try:
                    candidate = json.loads(line[marker + 8:])
                    if isinstance(candidate, dict) and candidate.get('type') in ('metric', 'progress', 'token', 'result', 'status', 'model_state'):
                        event = candidate
                except ValueError: pass
            self.store.event(key, event)
            if event.get('type') == 'model_state' and event.get('phase') in ('loading', 'generating', 'unloading'):
                with self.mutex:
                    current = self.store.get('job', key)
                    current['model_state'] = event['phase']
                    self.store.put('job', current)
            if collect and sum(map(len, chunks)) < 2000000: chunks.append(line)
        returncode = process.wait()
        with self.mutex:
            current = self.store.get('job', key)
            current.pop('pid', None); current.pop('pid_started', None); self.store.put('job', current)
            if current['kind'] == 'inference':
                current['model_state'] = 'unloaded'; self.store.put('job', current)
                self.store.event(key, {'type': 'model_state', 'phase': 'unloaded', 'text': '推理进程已退出，模型已卸载'})
            cancelled = current['state'] == 'cancelling'
        if cancelled: raise InterruptedError('任务已取消，执行进程已退出')
        if returncode: raise RuntimeError(f'执行进程退出码 {returncode}，请查看任务日志')
        return '\n'.join(chunks)

    def _worker(self, job, run):
        folder = Path(job['output_dir']); config = job['config']
        if job['kind'] == 'ablation':
            rendered = compose(config['toml'], config['fields'], config['model'], folder)
            (folder / 'abliterix.toml').write_text(rendered, encoding='utf-8')
        snapshot = {**config, 'kind': job['kind'], 'output_dir': str(folder)}
        (folder / 'request.json').write_text(json.dumps(snapshot, ensure_ascii=False), encoding='utf-8')
        if job['kind'] == 'inference' and config.get('workflow') == 'chat': return self.llm.execute(job)
        self.llm.evict_idle()
        python = str(interpreter(config['runtime_path']))
        if job['kind'] == 'ablation':
            run([python, str(WORKERS / 'ablation_worker.py'), str(folder / 'request.json')])
        else:
            run([python, str(WORKERS / 'execute.py'), str(folder / 'request.json')])
        result_path = folder / 'result.json'
        if not result_path.is_file(): raise RuntimeError('进程结束但未提交结果清单')
        result = json.loads(result_path.read_text(encoding='utf-8'))
        if not isinstance(result, dict): raise RuntimeError('结果清单格式无效')
        return result

    def cancel(self, key):
        with self.mutex:
            job = self.store.get('job', key)
            if job['state'] in TERMINAL and not process_alive(job): return job
            if key not in self.active and not process_alive(job):
                job.update(state='cancelled', finished_at=time.time()); self.targets.pop(key, None)
                self.store.put('job', job); self.wake.set(); return job
            job['state'] = 'cancelling'; self.store.put('job', job)
            (Path(job['output_dir']) / 'pause.request').unlink(missing_ok=True)
            if process_alive(job):
                parent = psutil.Process(job['pid'])
                children = parent.children(recursive=True)
                for proc in reversed(children):
                    try: proc.terminate()
                    except psutil.NoSuchProcess: pass
                try: parent.terminate()
                except psutil.NoSuchProcess: pass
                _, alive = psutil.wait_procs([*children, parent], timeout=3)
                for proc in alive:
                    try: proc.kill()
                    except psutil.NoSuchProcess: pass
                _, alive = psutil.wait_procs(alive, timeout=3)
                if alive: raise ValueError('进程尚未确认退出，请稍后重试取消')
            if job.get('finished_at'):
                job['state'] = 'cancelled'; self.store.put('job', job)
            return job

    def preview(self, key):
        job = self.store.get('job', key)
        file = (job.get('result') or {}).get('file')
        if not file: raise ValueError('没有可预览产物')
        path = Path(file).resolve()
        if not path.is_relative_to(Path(job['output_dir']).resolve()) or not path.is_file(): raise ValueError('产物路径无效')
        mime = {'.png': 'image/png', '.mp4': 'video/mp4'}.get(path.suffix)
        if not mime or path.stat().st_size > 5 * 1024 * 1024: raise ValueError('产物超过 5 MiB 预览上限或类型不支持，请从结果目录打开')
        return {'mime': mime, 'data': base64.b64encode(path.read_bytes()).decode()}

    def close(self):
        with self.mutex: self.stopping = True
        self.wake.set(); self.scheduler.join(timeout=2)
        for job in self.store.list('job', 100000):
            if job['state'] not in TERMINAL or process_alive(job): self.cancel(job['id'])
        for thread in list(self.threads): thread.join(timeout=10)
        self.llm.close()
        if not self.threads: self.store.close()


def decode_image(value):
    match = re.fullmatch(r'data:image/(png|jpeg|webp);base64,([A-Za-z0-9+/=]+)', value)
    if not match: raise ValueError('图片必须为 PNG/JPEG/WebP 数据，不能使用外部 URL')
    try: data = base64.b64decode(match[2], validate=True)
    except ValueError as exc: raise ValueError('图片编码无效') from exc
    if len(data) > 650000: raise ValueError('图片过大，请缩小到 650 KB 内')
    return data
