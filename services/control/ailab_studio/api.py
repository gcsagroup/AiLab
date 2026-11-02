"""Same authenticated API for desktop host and local development bridge."""
import time
from fastapi import APIRouter, Query
from . import contracts as C
from .ablation import templates, compose
from .catalog import recommend
from .compatibility import check_model
from .storage import uid


def router(studio):
    api = APIRouter(prefix='/api/v1/studio')

    @api.get('/status')
    def status():
        from .catalog import storage_info
        return {'hardware': {**studio.hardware, **storage_info(studio.environment)}, 'runtimes': studio.runtimes.list(), 'paths': studio.paths(), 'environment_dir': str(studio.environment), 'default_environment_dir': str(studio.default_environment)}

    @api.post('/environment')
    def environment(payload: C.EnvironmentPath): return studio.save_environment(payload.path)

    @api.get('/settings')
    def settings(): return studio.settings()

    @api.post('/settings')
    def save_settings(payload: C.Settings): return studio.save_settings(payload.model_dump())

    @api.post('/paths')
    def paths(payload: C.Paths): return studio.save_paths(payload.model_dump())

    @api.get('/assets')
    def assets(): return studio.assets()

    @api.post('/recommend')
    def recommendations(payload: C.Recommendation):
        result = recommend(payload.model, payload.engine, studio.hardware)
        try: runtime = studio.runtimes.resolve(payload.engine)
        except ValueError: runtime = None
        if runtime and runtime.get('accelerator') == 'cpu':
            result['config']['device'] = 'cpu'
            if payload.engine == 'llama': result['config']['gpu_layers'] = 0
            result['notes'].append('当前安装的是 CPU 环境，推荐使用 CPU。')
        return result

    @api.post('/runtimes/{profile}/install')
    def install(profile: str, payload: C.Install): return studio.runtimes.install(profile, payload.accelerator)

    @api.get('/jobs')
    def jobs():
        return {'items': [{k: v for k, v in j.items() if k not in ('config', 'result')} for j in studio.jobs()]}

    @api.get('/jobs/{key}')
    def job(key: str): return studio.store.get('job', key)

    @api.get('/jobs/{key}/events')
    def events(key: str, after: int = Query(default=0, ge=0)):
        studio.store.get('job', key)
        return {'items': studio.store.events(key, after)}

    @api.post('/jobs/{key}/cancel')
    def cancel(key: str): return studio.cancel(key)

    @api.post('/jobs/{key}/pause')
    def pause(key: str): return studio.pause(key)

    @api.post('/jobs/{key}/resume')
    def resume(key: str): return studio.resume(key)

    @api.get('/jobs/{key}/preview')
    def preview(key: str): return studio.preview(key)

    @api.post('/sft')
    def sft(payload: C.SFT): return studio.submit('sft', payload)

    @api.post('/inference')
    def inference(payload: C.Inference): return studio.submit('inference', payload)

    @api.get('/llm/status')
    def llm_status(): return studio.llm.status()

    @api.post('/llm/capabilities')
    def llm_capabilities(payload: C.ModelCapabilities):
        from .catalog import model_info, local_path
        info = model_info(payload.model)
        supported = bool(info.get('vision')) if payload.engine == 'vllm' else bool(payload.vision_handler != 'none' and payload.mmproj and local_path(payload.mmproj).is_file())
        return {'vision': supported, 'reason': '' if supported else '当前模型未启用视觉能力，仅支持文本消息'}

    @api.post('/llm/load')
    def llm_load(payload: C.Inference):
        if payload.workflow != 'chat' or payload.action != 'load': raise ValueError('请使用 LLM 加载请求')
        return studio.submit('inference', payload)

    @api.post('/llm/unload')
    def llm_unload(): return studio.llm.unload()

    @api.get('/ablation/template')
    def template(): return templates()

    @api.post('/ablation/compatibility')
    def compatibility(payload: C.ModelCheck): return check_model(studio, payload.model)

    @api.post('/ablation/validate')
    def validate(payload: C.Ablation):
        return {'toml': compose(payload.toml, payload.fields, payload.model, studio.root / 'jobs' / 'preview')}

    @api.post('/ablation')
    def ablation(payload: C.Ablation): return studio.submit('ablation', payload)

    @api.get('/conversations')
    def conversations(): return {'items': [{k: v for k, v in item.items() if k != 'messages'} for item in studio.store.list('conversation')]}

    @api.get('/conversations/{key}')
    def read_conversation(key: str): return studio.store.get('conversation', key)

    @api.post('/conversations')
    def conversation(payload: C.Conversation):
        with studio.mutex:
            for job in studio.store.list('job', 100000):
                if job.get('config', {}).get('conversation_id') and job['state'] not in ('succeeded', 'failed', 'cancelled', 'interrupted'):
                    studio.cancel(job['id'])
            for item in studio.store.list('conversation', 100000): studio.store.delete('conversation', item['id'])
            return studio.store.put('conversation', {'id': uid(), **payload.model_dump(), 'updated_at': time.time()})

    @api.post('/conversations/{key}')
    def save_conversation(key: str, payload: C.Conversation):
        with studio.mutex:
            studio.store.get('conversation', key)
            return studio.store.put('conversation', {'id': key, **payload.model_dump(), 'updated_at': time.time()})

    @api.get('/materials')
    def materials(): return {'items': studio.store.list('material', 100000)}

    @api.delete('/materials/{key}')
    def delete_material(key: str): return studio.materials.delete(key)

    @api.post('/materials/import')
    def import_material(payload: C.MaterialImport):
        from .catalog import local_path
        return studio.materials.add(local_path(payload.path), 'imported', name=payload.name)

    @api.post('/materials/uploads')
    def upload(payload: C.UploadStart): return studio.materials.begin(payload.name, payload.size)

    @api.post('/materials/uploads/{key}/chunk')
    def chunk(key: str, payload: C.UploadChunk): return studio.materials.append(key, payload.offset, payload.data)

    @api.post('/materials/uploads/{key}/complete')
    def complete(key: str): return studio.materials.complete(key)

    @api.get('/materials/{key}/content')
    def content(key: str, offset: int = Query(default=0, ge=0), length: int = Query(default=524288, ge=1, le=524288)):
        return studio.materials.content(key, offset, length)

    @api.get('/materials/{key}/thumbnail')
    def thumbnail(key: str): return studio.materials.thumbnail(key)

    return api
