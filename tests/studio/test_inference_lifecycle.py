import importlib.util
import json
from pathlib import Path
import sys
import time
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'services/control'))
from ailab_studio.service import Studio
from ailab_studio.contracts import Inference


def test_cpu_offload_placement(monkeypatch):
    workers = Path(__file__).resolve().parents[2] / 'services/control/ailab_studio/workers'
    monkeypatch.syspath_prepend(str(workers))
    spec = importlib.util.spec_from_file_location('tested_inference', workers / 'inference.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    pipe = Mock()
    assert module.place_pipeline(pipe, 'cuda', True) == 'model_cpu_offload'
    pipe.enable_model_cpu_offload.assert_called_once_with()
    pipe.to.assert_not_called()  # Never allocate the whole pipeline on GPU before offloading.
    pipe.reset_mock()
    assert module.place_pipeline(pipe, 'cpu', True) == 'disabled'
    pipe.enable_model_cpu_offload.assert_not_called(); pipe.to.assert_called_once_with('cpu')
    pipe.reset_mock()
    module.place_pipeline(pipe, 'cuda', False)
    pipe.enable_model_cpu_offload.assert_not_called(); pipe.to.assert_called_once_with('cuda')
    config = Inference(model='local', workflow='t2i', engine='diffusers', prompt='test')
    assert config.cpu_offload is True and config.cpu_offload_gb == 4


def test_model_lifecycle_uses_process_exit(tmp_path):
    studio = Studio(tmp_path)
    script = "import time\nprint('@@AILAB " + json.dumps({'type': 'model_state', 'phase': 'loading'}) + "',flush=True)\ntime.sleep(.6)\nprint('@@AILAB " + json.dumps({'type': 'model_state', 'phase': 'generating'}) + "',flush=True)\ntime.sleep(.6)\nprint('@@AILAB " + json.dumps({'type': 'model_state', 'phase': 'unloading'}) + "',flush=True)\ntime.sleep(.6)"
    try:
        job = studio.launch('inference', {}, 'llama', lambda j, run: run([sys.executable, '-u', '-c', script]))
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            current = studio.store.get('job', job['id'])
            if current['state'] == 'succeeded': break
            time.sleep(.05)
        assert current['state'] == 'succeeded' and current['model_state'] == 'unloaded'
        phases = [event['phase'] for event in studio.store.events(job['id']) if event['type'] == 'model_state']
        assert phases == ['loading', 'generating', 'unloading', 'unloaded']
        assert 'pid' not in current
    finally: studio.close()
