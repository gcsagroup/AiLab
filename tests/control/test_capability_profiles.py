"""冷启动能力探测：三个独立profile并行，图片视频共享。"""
from concurrent.futures import ThreadPoolExecutor
import threading

from test_control import rig


def test_capabilities_probe_three_profiles_concurrently_once(rig, monkeypatch):
    client, service, *_ = rig
    gate = threading.Barrier(3)
    calls = []
    def probe(kind, refresh=False, **_):
        calls.append(kind)
        gate.wait(timeout=3)
        return {'ready': True, 'reason': '', 'engine': {'text': 'mlx', 'image': 'diffusers', 'audio': 'kokoro'}[kind], 'device_id': 'cpu' if kind == 'audio' else 'apple-gpu'}
    monkeypatch.setattr(service, 'environment', lambda refresh=False, **_: probe('text', refresh=refresh))
    monkeypatch.setattr(service.media, 'environment', probe)
    response = client.get('/api/v1/capabilities')
    assert response.status_code == 200
    assert sorted(calls) == ['audio', 'image', 'text']
    items = response.json()['items']
    assert next(x for x in items if x['kind'] == 'video' and x['operation'] == 'generate')['supported'] is True
    assert next(x for x in items if x['kind'] == 'audio' and x['operation'] == 'train')['supported'] is False


def test_media_profile_locks_serialize_shared_profile_not_audio(rig, monkeypatch):
    media = rig[1].media
    entered = threading.Event(); release = threading.Event(); audio = threading.Event(); video = threading.Event()
    def inspect(kind, refresh=False, observation=None):
        if kind == 'image':
            entered.set(); assert release.wait(3)
        elif kind == 'audio': audio.set()
        else: video.set()
        return {'kind': kind}
    monkeypatch.setattr(media, '_environment', inspect)
    with ThreadPoolExecutor(max_workers=3) as pool:
        image_job = pool.submit(media.environment, 'image')
        assert entered.wait(3)
        video_job = pool.submit(media.environment, 'video')
        audio_job = pool.submit(media.environment, 'audio')
        assert audio.wait(3)
        assert not video.is_set()
        release.set()
        assert [future.result()['kind'] for future in (image_job, video_job, audio_job)] == ['image', 'video', 'audio']
