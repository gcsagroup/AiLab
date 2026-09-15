"""将固定 CPU 中文配音接入统一运行快照与媒体产物合同。"""

import argparse
import json
import os
from pathlib import Path
import signal
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'adapters/media'))
sys.path.insert(0, str(ROOT / 'services/control'))
import tts_cli as tts
from ailab_control.media_assets import media_model_manifest
from ailab_control.storage import Fault


def watch_controller():
    raw = os.environ.get('AILAB_CONTROL_PID')
    if not raw:
        return
    if not raw.isdigit() or int(raw) <= 1 or os.getppid() != int(raw):
        raise tts.TTSError('INVALID_CONTROLLER', '配音执行器父进程身份不匹配。')
    controller = int(raw)

    def watch():
        while True:
            time.sleep(0.5)
            if os.getppid() != controller:
                os.kill(os.getpid(), signal.SIGTERM)
                # 底层推理算子若不返回，仍在固定上限内回收自己的进程。
                time.sleep(10)
                os._exit(130)

    threading.Thread(target=watch, daemon=True).start()


def inspect(snapshot, output):
    report = media_model_manifest(Path(snapshot.get('model_path', '')))
    if not report or report['modality'] != 'audio' or report['manifest'] != snapshot.get('model_manifest') or report['manifest_digest'] != snapshot.get('model_manifest_digest') or report['metadata_manifest_digest'] != snapshot.get('prepared_model_manifest_digest'):
        raise tts.TTSError('MODEL_IDENTITY_CHANGED', '配音模型的完整导入清单与固定官方来源不一致。')
    internal = {key: snapshot[key] for key in ('kind', 'operation', 'model_path', 'runtime', 'input')}
    internal['model_manifest_digest'] = report['metadata_manifest_digest']
    _, effective = tts.validate(internal, output / 'result')
    for key in ('phonemization_digest', 'environment_manifest_digest', 'executor_manifest_digest'):
        internal[key] = effective[key]
    recipe = {'schema_version': 'kokoro-control-v1', 'model_manifest_digest': report['manifest_digest'], 'prepared_model_manifest_digest': report['metadata_manifest_digest'], 'runtime': snapshot['runtime'], 'input': snapshot['input'], 'phonemization_digest': effective['phonemization_digest'], 'environment_manifest_digest': effective['environment_manifest_digest'], 'executor_manifest_digest': effective['executor_manifest_digest'], 'bridge_sha256': tts.file_hash(Path(__file__))}
    recipe_digest = tts.digest(recipe)
    if snapshot.get('media_recipe_digest', recipe_digest) != recipe_digest:
        raise tts.TTSError('MEDIA_RECIPE_CHANGED', '提交后的配音配方或执行环境已变化。')
    effective.update(prepared_model_manifest_digest=report['metadata_manifest_digest'], model_manifest_digest=report['manifest_digest'], media_recipe_digest=recipe_digest)
    return internal, {'can_submit': True, 'blocking': [], 'effective_config': effective, 'recipe': recipe, 'media_recipe_digest': recipe_digest, 'check_report': {'model': 'fixed_official_verified', 'phonemes': 'passed', 'output': 'new_directory', 'quality': 'not_evaluated'}}


def main():
    parser = argparse.ArgumentParser(description='固定 CPU 中文配音工作进程')
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--preflight', action='store_true')
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, tts.cancelled)
    signal.signal(signal.SIGINT, tts.cancelled)
    try:
        watch_controller()
        snapshot = json.loads(args.snapshot.read_text())
        output = args.output_dir.absolute()
        with tts.offline_mode():
            internal, check = inspect(snapshot, output)
            if args.preflight:
                print(json.dumps(check, ensure_ascii=False))
                return 0
            if not snapshot.get('attempt_id') or snapshot.get('media_recipe_digest') != check['media_recipe_digest']:
                raise tts.TTSError('MEDIA_RECIPE_REQUIRED', '执行须绑定已检查的运行身份与配音配方。')
            if output.exists() and (not output.is_dir() or any(output.iterdir())):
                raise tts.TTSError('OUTPUT_NOT_ALLOWED', '统一执行输出目录必须为空。')
            output.mkdir(parents=True, exist_ok=True)
            original_emit = tts.emit

            def forward(kind, **fields):
                if kind != 'completed':
                    original_emit(kind, **fields)

            tts.emit = forward
            try:
                report = tts.synthesize(internal, output / 'result')
            finally:
                tts.emit = original_emit
            inspect(snapshot, output.parent / ('postcheck-' + snapshot['attempt_id']))
            effective = {**report['effective_config'], **{key: check['effective_config'][key] for key in ('model_manifest_digest', 'prepared_model_manifest_digest', 'media_recipe_digest')}}
            (output / 'effective-config.json').write_text(json.dumps(effective, ensure_ascii=False, indent=2) + '\n')
            evidence = {'schema_version': 'media-execution-v1', 'attempt_id': snapshot['attempt_id'], 'source_snapshot_digest': tts.digest(snapshot), 'media_recipe_digest': check['media_recipe_digest'], 'source_model_unchanged': True, 'primary_artifact': 'result/speech.wav', 'quality_status': 'not_evaluated'}
            (output / 'execution-evidence.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n')
            artifacts = [{'path': name, 'sha256': tts.file_hash(output / name), 'media_type': mime} for name, mime in [('result/speech.wav', 'audio/wav'), ('result/tts-report.json', 'application/json'), ('effective-config.json', 'application/json'), ('execution-evidence.json', 'application/json')]]
            tts.emit('completed', artifacts=artifacts, effective_config=effective, source_model_unchanged=True)
        return 0
    except (tts.TTSError, Fault, ValueError, OSError) as error:
        code = getattr(error, 'code', 'TTS_FAILED')
        message = getattr(error, 'message', str(error))
        if args.preflight:
            print(json.dumps({'can_submit': False, 'blocking': [{'code': code, 'message': message}]}, ensure_ascii=False))
        else:
            tts.emit('error', code=code, message=message)
        return 130 if code == 'CANCELLED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
