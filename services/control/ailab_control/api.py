"""固定业务 HTTP 接口；普通网页不获得本机执行权。"""

import asyncio
import hmac
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, Header, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_serializer, model_validator
from starlette.exceptions import HTTPException

from .service import Service
from .storage import Fault
from .ui_context import UIContextPatch


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class ProjectInput(Strict):
    name: str = Field(min_length=1, max_length=120, pattern=r"\S")


class ProjectEdit(ProjectInput):
    expected_revision: int = Field(ge=1)


class GrantInput(Strict):
    path: str = Field(min_length=1, max_length=4096)


class ImportPlanInput(GrantInput):
    project_id: str
    name: str | None = Field(default=None, min_length=1, max_length=120)
    grant_id: str | None = None
    schema_name: Literal["sft", "cpt", "image_caption_v1"] = Field(default="sft", alias="schema")


class ImportInput(Strict):
    plan_id: str
    manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class Runtime(Strict):
    engine: str = Field(default="mlx", max_length=40)
    device_id: str = Field(default="apple-gpu", max_length=100)
    max_tokens: int = Field(default=128, ge=1, le=2048)
    temperature: float = Field(default=0, ge=0, le=2)
    top_p: float = Field(default=1, ge=0.01, le=1)
    seed: int = Field(default=0, ge=0, le=2**32 - 1)
    kv_precision: Literal['auto', 'q4'] = 'auto'
    prefill_step_size: Literal[512, 2048, 4096] = 2048
    context_limit: int = Field(default=4096, ge=128, le=4096)
    overflow: Literal['reject'] = 'reject'
    stop: list[str] = Field(default_factory=list, max_length=8)
    stream: bool = True
    thinking: Literal['default'] = 'default'

    @field_validator('stop')
    @classmethod
    def stop_sequences(cls, value):
        if len(set(value)) != len(value):
            raise ValueError('停止序列不能重复')
        for text in value:
            if not 1 <= len(text) <= 128:
                raise ValueError('每个停止序列必须是 1—128 个字符；空格按原样保留')
            text.encode('utf-8')
            if any((ord(char) < 32 and char not in '\n\t') or ord(char) == 127 for char in text):
                raise ValueError('停止序列不能包含控制字符；换行与制表符除外')
        return value

    @field_validator('prefill_step_size', mode='before')
    @classmethod
    def integer_prefill(cls, value):
        if type(value) is not int:
            raise ValueError('提示词分块上限必须为整数')
        return value

    @model_serializer(mode='wrap')
    def preserve_legacy_fields(self, handler):
        result = handler(self)
        # 旧草稿省略的字段继续省略，实际默认值由检查器固定保存。
        for name in ('kv_precision', 'prefill_step_size', 'context_limit', 'overflow', 'stop', 'stream', 'thinking'):
            if name not in self.model_fields_set:
                result.pop(name, None)
        return result


class TrainingRuntime(Strict):
    engine: str = Field(default="mlx", max_length=40)
    device_id: str = Field(default="apple-gpu", max_length=100)
    seed: int = Field(default=0, ge=0, le=2**32 - 1)
    training_type: Literal["sft"] = "sft"
    update_method: Literal["lora"] = "lora"
    recipe_id: Literal["qwen25-assistant-only-v1"] = "qwen25-assistant-only-v1"
    steps: int = Field(default=4, ge=1, le=200)
    learning_rate: float = Field(default=0.0001, ge=1e-7, le=0.01)
    max_seq_length: int = Field(default=512, ge=32, le=2048)
    lora_rank: int = Field(default=4, ge=1, le=32)
    lora_alpha: float = Field(default=8, ge=1, le=64)
    num_layers: int = Field(default=2, ge=1, le=28)
    batch_size: int = Field(default=1, ge=1, le=1)
    gradient_accumulation: int = Field(default=1, ge=1, le=1)
    optimizer: Literal["adamw"] = "adamw"
    weight_decay: float = Field(default=0, ge=0, le=0)
    lora_dropout: float = Field(default=0, ge=0, le=0)


class DatasetSplitPrepare(Strict):
    project_id: str = Field(min_length=1, max_length=100)
    source_dataset_id: str = Field(min_length=1, max_length=100)
    model_id: str = Field(min_length=1, max_length=100)
    max_seq_length: int
    split_seed: int = Field(ge=0, le=2**32 - 1)
    validation_fraction_bps: int = Field(ge=1, le=9999)

    @field_validator('max_seq_length')
    @classmethod
    def training_length(cls, value):
        return TrainingRuntime(max_seq_length=value).max_seq_length


class DatasetSplitApply(Strict):
    plan_id: str = Field(pattern=r'^dataset-split-plan-[0-9a-f]{32}$')
    plan_digest: str = Field(pattern=r'^[0-9a-f]{64}$')


class NvidiaRuntime(Strict):
    engine: Literal['transformers'] = 'transformers'
    device_id: Literal['cuda:0'] = 'cuda:0'
    precision: Literal['bfloat16'] = 'bfloat16'
    max_tokens: int = Field(default=128, ge=1, le=512)
    temperature: float = Field(default=0, ge=0, le=2)
    top_p: float = Field(default=1, ge=0.01, le=1)
    seed: int = Field(default=0, ge=0, le=2**32 - 1)
    context_limit: int = Field(default=4096, ge=128, le=4096)
    overflow: Literal['reject'] = 'reject'
    stop: list[str] = Field(default_factory=list, max_length=8)
    stream: bool = True
    thinking: Literal['default'] = 'default'

    @field_validator('stop')
    @classmethod
    def stop_sequences(cls, value):
        return Runtime.stop_sequences(value)


class NvidiaTrainingRuntime(TrainingRuntime):
    num_layers: int = Field(default=2, ge=1, le=24)
    engine: Literal['transformers'] = 'transformers'
    device_id: Literal['cuda:0'] = 'cuda:0'
    precision: Literal['bfloat16'] = 'bfloat16'
    learning_rate: float = Field(default=0.0001, ge=1e-6, le=0.01)
    lora_alpha: int = Field(default=8, ge=1, le=64)

    @field_validator('lora_alpha', mode='before')
    @classmethod
    def integral_alpha(cls, value):
        # 旧草稿会保存为8.0；仅保留原有的无损整数转换，不接受小数或布尔值。
        return int(value) if type(value) is float and value.is_integer() else value


def training_contracts():
    """从实际草稿校验声明生成训练范围；读取配置不触发设备或依赖探测。"""
    units = {'steps': 'updates', 'learning_rate': 'learning_rate', 'max_seq_length': 'tokens',
             'lora_rank': 'rank', 'lora_alpha': 'scale', 'num_layers': 'layers', 'seed': 'seed',
             'batch_size': 'samples', 'gradient_accumulation': 'micro_batches',
             'optimizer': 'optimizer', 'weight_decay': 'ratio', 'lora_dropout': 'ratio'}
    items = []
    for runtime, name, scope, label in (
            (TrainingRuntime, 'mlx', 'local', '内置 Apple MLX SFT LoRA 配方'),
            (NvidiaTrainingRuntime, 'nvidia', 'remote', '内置 NVIDIA SFT LoRA 配方')):
        properties = runtime.model_json_schema()['properties']
        parameters = {}
        for field, unit in units.items():
            declared = properties[field]
            parameter = {key: declared[key] for key in ('type', 'default', 'minimum', 'maximum', 'enum') if key in declared}
            if 'const' in declared:
                parameter['enum'] = [declared['const']]
            parameter.update(unit=unit, editable=declared['type'] in {'integer', 'number'} and declared.get('minimum') != declared.get('maximum'))
            parameters[field] = parameter
        contract_id = f'qwen25-{name}-sft-lora-v1'
        items.append({'schema_version': 'ailab-training-contract-v1', 'id': contract_id,
                      'kind': 'text', 'operation': 'train', 'engine': properties['engine']['default'],
                      'device_id': properties['device_id']['default'], 'execution_scope': scope,
                      'model_constraint': ('Qwen2.5-0.5B-Instruct（最多24层）或 Qwen2.5-7B-Instruct（最多28层）原权重；不支持量化基座训练' if name == 'mlx' else 'Qwen2.5-0.5B-Instruct 原权重；不支持量化基座训练'),
                      'training_type': 'sft', 'update_method': 'lora', 'recipe_id': 'qwen25-assistant-only-v1',
                      'source': {'id': contract_id, 'label': label, 'default_source': 'versioned_control_schema',
                                 'constraint_source': 'control_and_worker_intersection'},
                      'parameters': parameters,
                      'application_policy': {'applies_to': 'next_run', 'restart_required': False,
                                             'saved_values': 'preserve_and_validate', 'conflicts': []},
                      'stopping': {'mode': 'steps', 'sample_order': 'file_cycle', 'data_parallel_devices': 1,
                                   'effective_batch_size': 1},
                      'verification': {'device_execution': 'requires_preflight', 'quality': 'not_implied'}})
    return items


class TextInput(Strict):
    prompt: str = Field(default="", max_length=16000)


class ImageInput(Strict):
    prompt: str = Field(default='', max_length=2000)
    negative_prompt: str = Field(default='', max_length=2000)


class VideoInput(Strict):
    material_id: str | None = None


class ImageRuntime(Strict):
    engine: Literal['diffusers'] = 'diffusers'
    device_id: Literal['apple-gpu'] = 'apple-gpu'
    seed: int = Field(default=0, ge=0, le=2**32 - 1)
    size: Literal[512] = 512
    steps: Literal[20] = 20
    cfg: float = Field(default=7.5, ge=7.5, le=7.5)


class ImageTrainingRuntime(Strict):
    engine: Literal['diffusers'] = 'diffusers'
    device_id: Literal['apple-gpu'] = 'apple-gpu'
    seed: int = Field(default=0, ge=0, le=2**32 - 1)
    size: Literal[512] = 512
    steps: Literal[12] = 12
    learning_rate: float = Field(default=0.0001, ge=0.0001, le=0.0001)
    lora_rank: Literal[4] = 4


class VideoRuntime(Strict):
    engine: Literal['diffusers'] = 'diffusers'
    device_id: Literal['apple-gpu'] = 'apple-gpu'
    seed: int = Field(default=0, ge=0, le=2**32 - 1)
    steps: Literal[25] = 25
    frames: Literal[14] = 14
    fps: Literal[7] = 7


class AudioRuntime(Strict):
    engine: Literal['kokoro'] = 'kokoro'
    device_id: Literal['cpu'] = 'cpu'
    seed: int = Field(default=0, ge=0, le=2**32 - 1)
    voice: Literal['zf_xiaobei'] = 'zf_xiaobei'
    speed: float = Field(default=1, ge=0.5, le=2)
    sample_rate: Literal[24000] = 24000


class Draft(Strict):
    kind: Literal["text", "image", "video", "audio"]
    operation: Literal["generate", "train"]
    model_id: str | None = None
    dataset_id: str | None = None
    adapter_id: str | None = None
    evaluation_plan_id: str | None = None
    checkpoint_id: str | None = None
    execution_target_id: str | None = None
    input: TextInput | ImageInput | VideoInput = Field(default_factory=TextInput)
    runtime: Runtime | TrainingRuntime | NvidiaRuntime | NvidiaTrainingRuntime | ImageRuntime | ImageTrainingRuntime | VideoRuntime | AudioRuntime

    @model_validator(mode="after")
    def correct_operation(self):
        required = {('text', 'train'): ((TrainingRuntime, NvidiaTrainingRuntime), TextInput), ('text', 'generate'): ((Runtime, NvidiaRuntime), TextInput), ('image', 'generate'): (ImageRuntime, ImageInput), ('image', 'train'): (ImageTrainingRuntime, ImageInput), ('video', 'generate'): (VideoRuntime, VideoInput), ('audio', 'generate'): (AudioRuntime, TextInput)}
        runtime, inputs = required.get((self.kind, self.operation), (None, None))
        if runtime is None or not isinstance(self.runtime, runtime) or not isinstance(self.input, inputs):
            raise ValueError('任务类型需要对应的输入和执行参数')
        if self.kind == 'text' and self.runtime.engine == 'transformers':
            selected = NvidiaTrainingRuntime if self.operation == 'train' else NvidiaRuntime
            # 不让缺省precision的远端请求落入更宽的本机联合类型。
            if not isinstance(self.runtime, selected):
                self.runtime = selected.model_validate(self.runtime.model_dump())
        return self


class TaskInput(ProjectInput):
    project_id: str
    kind: Literal["text", "image", "video", "audio"]
    operation: Literal["generate", "train"]


class DraftEdit(Strict):
    expected_revision: int = Field(ge=1)
    draft: Draft


class PreflightInput(Strict):
    draft_revision: int = Field(ge=1)


class SubmitInput(Strict):
    preflight_id: str
    expected_revision: int = Field(ge=1)


class ControlInput(Strict):
    expected_state_version: int = Field(ge=1)


class CheckpointTaskInput(Strict):
    name: str | None = Field(default=None, min_length=1, max_length=160)


class EmptyInput(Strict):
    pass


class ExecutionTargetInput(ProjectInput):
    project_id: str = Field(min_length=1, max_length=100)
    origin: str = Field(min_length=1, max_length=2048)
    transport: Literal['loopback_http', 'https'] = 'loopback_http'
    executor_id: str = Field(min_length=1, max_length=100)
    credential_token: str = Field(min_length=32, max_length=512, repr=False)


class HostExecutionTargetInput(ExecutionTargetInput):
    credential_ref: str = Field(pattern=r'^remote-credential-[0-9a-f]{32}$')


class ExecutionCredentialInput(Strict):
    credential_token: str = Field(min_length=32, max_length=512, repr=False)
    expected_revision: int = Field(ge=1)


class HostExecutionCredentialInput(ExecutionCredentialInput):
    credential_ref: str = Field(pattern=r'^remote-credential-[0-9a-f]{32}$')


class ExecutionCredentialDelete(Strict):
    expected_revision: int = Field(ge=1)


class ExecutionCredentialCleanup(ExecutionCredentialDelete):
    credential_ref: str = Field(pattern=r'^remote-credential-[0-9a-f]{32}$')


class RemoteTransferPrepare(Strict):
    project_id: str = Field(min_length=1, max_length=100)
    execution_target_id: str = Field(min_length=1, max_length=100)
    asset_kind: Literal['dataset', 'material']
    asset_id: str = Field(min_length=1, max_length=100)


class RemoteTransferSubmit(Strict):
    prepare_id: str = Field(min_length=1, max_length=100)
    digest: str = Field(pattern=r'^[0-9a-f]{64}$')


class ExecutionDefaultInput(Strict):
    execution_target_id: str | None
    expected_revision: int = Field(ge=1)


class ModelDownloadInput(Strict):
    project_id: str = Field(min_length=1)
    catalog_id: str = Field(min_length=1)
    manifest_digest: str = Field(pattern=r'^[0-9a-f]{64}$')


class WorkflowConfiguration(Strict):
    model_id: str = Field(min_length=1)
    input: dict[str, str] = Field(default_factory=dict)
    runtime: dict[str, str | int | float] = Field(default_factory=dict)


class WorkflowSteps(Strict):
    image: WorkflowConfiguration
    video: WorkflowConfiguration
    audio: WorkflowConfiguration


class WorkflowStart(ProjectInput):
    project_id: str = Field(min_length=1)
    definition_version: str = Field(min_length=1, max_length=80)
    steps: WorkflowSteps


class WorkflowInputEdit(Strict):
    expected_revision: int = Field(ge=1)
    configuration: WorkflowConfiguration


class WorkflowAdvance(Strict):
    expected_revision: int = Field(ge=1)
    step_attempt_id: str = Field(min_length=1)
    input_revision: int = Field(ge=1)
    artifact_ids: list[str] = Field(min_length=1, max_length=1)


class WorkflowReuse(Strict):
    expected_revision: int = Field(ge=1)
    step_id: Literal['image', 'video', 'audio']
    input_revision: int = Field(ge=1)
    source_attempt_id: str = Field(min_length=1)
    artifact_id: str = Field(min_length=1)


class WorkflowSave(Strict):
    expected_revision: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=120, pattern=r'\S')


class CleanupInput(Strict):
    plan_id: str
    plan_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class CollectionInput(Strict):
    manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_collection_version: int = Field(ge=0)


class WorkInput(Strict):
    attempt_id: str
    artifact_id: str | None = None
    name: str | None = Field(default=None, min_length=1, max_length=120)


class WorkReuseInput(Strict):
    project_id: str = Field(min_length=1)
    name: str | None = Field(default=None, min_length=1, max_length=120, pattern=r'\S')


class WorkFavoriteInput(Strict):
    project_id: str = Field(min_length=1)
    favorite: bool


class WorkRevisionInput(Strict):
    expected_revision: int = Field(ge=1)
    parent_revision_id: str | None
    content_kind: Literal['text', 'voice_script', 'subtitles']
    content: dict


class AIRequestInput(Strict):
    target_task_id: str
    expected_revision: int = Field(ge=1)
    model_id: str
    instruction: str = Field(min_length=1, max_length=2000, pattern=r'\S')


class AIResponseInput(Strict):
    attempt_id: str


class AIRevisionInput(Strict):
    expected_revision: int = Field(ge=1)


class SettingsInput(Strict):
    worker_python: str | None = Field(default=None, min_length=1, max_length=4096)
    media_python: str | None = Field(default=None, min_length=1, max_length=4096)
    audio_python: str | None = Field(default=None, min_length=1, max_length=4096)
    expected_revision: int = Field(ge=1)

    @model_validator(mode='after')
    def explicit_environment_change(self):
        if not self.model_fields_set.intersection({'worker_python', 'media_python', 'audio_python'}):
            raise ValueError('至少提供一个要更新的环境字段')
        return self


class AdapterInput(Strict):
    name: str | None = Field(default=None, min_length=1, max_length=120)


class ExportPlanInput(Strict):
    project_id: str
    object_type: Literal["model", "adapter", "work", "report", "dataset-split"]
    object_id: str
    target_dir: str = Field(min_length=1, max_length=4096)
    grant_id: str | None = None
    include_base: bool = False
    work_revision_id: str | None = Field(default=None, min_length=1)

    @model_validator(mode='after')
    def revision_belongs_to_work(self):
        if self.object_type != 'work' and self.work_revision_id is not None:
            raise ValueError('只有作品导出可以选择人工修订版本')
        return self


class ExportInput(Strict):
    plan_id: str
    plan_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class EvaluationGeneration(Strict):
    max_tokens: int = Field(ge=1, le=512)
    temperature: float = Field(ge=0, le=0)
    top_p: float = Field(ge=1, le=1)
    seed: int = Field(ge=0, le=2**32 - 1)


class CategoryThresholds(Strict):
    business: float = Field(gt=0, le=1)
    format: float = Field(gt=0, le=1)
    regression: float = Field(gt=0, le=1)
    behavior: float = Field(gt=0, le=1)


class EvaluationCriteria(Strict):
    schema_version: Literal["text-rules-v1"]
    category_min_pass_rate: CategoryThresholds
    regression_tolerance: float = Field(ge=0, le=1)
    generation: EvaluationGeneration


class EvaluationPlanInput(ProjectInput):
    project_id: str
    dataset_path: str = Field(min_length=1, max_length=4096)
    dataset_grant_id: str | None = None
    criteria: EvaluationCriteria


class EvaluationInput(Strict):
    project_id: str
    adapter_id: str | None = None
    candidate_model_id: str | None = None
    evaluation_plan_id: str
    name: str = Field(default="独立文本评测", min_length=1, max_length=120, pattern=r"\S")

    @model_validator(mode="after")
    def one_comparison_target(self):
        if bool(self.adapter_id) == bool(self.candidate_model_id):
            raise ValueError("评测须且只能选择一个适配器或量化模型")
        return self


class CandidateRegistration(Strict):
    evaluation_ids: list[str] = Field(default_factory=list, max_length=10)
    candidate_type: Literal["adapter", "quantized_model"] = "adapter"


class RestorePlanInput(Strict):
    backup_path: str = Field(min_length=1, max_length=4096)
    backup_grant_id: str | None = None
    target_dir: str = Field(min_length=1, max_length=4096)
    target_grant_id: str | None = None


class RestoreInput(Strict):
    plan_id: str
    plan_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class ConversionInput(Strict):
    project_id: str
    model_id: str
    name: str | None = Field(default=None, min_length=1, max_length=120, pattern=r"\S")


class DiagnosticPreviewInput(Strict):
    project_id: str | None = Field(default=None, min_length=1, max_length=100)
    attempt_ids: list[str] = Field(default_factory=list, max_length=20)


class DiagnosticExportInput(Strict):
    preview_id: str = Field(pattern=r'^diagnostic-preview-[0-9a-f]{32}$')
    target_dir: str = Field(min_length=1, max_length=4096)
    grant_id: str | None = None


def error_response(error):
    return JSONResponse({"error": {"code": error.code, "message": error.message, "details": error.details, "retryable": False}}, status_code=error.status)


def create_app(settings):
    service = Service(settings)

    @asynccontextmanager
    async def lifespan(app):
        yield
        await asyncio.to_thread(service.close)

    app = FastAPI(title="AI Lab 控制服务", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.service = service

    @app.middleware("http")
    async def local_boundary(request: Request, call_next):
        host = request.headers.get("host", "").split(":", 1)[0]
        if host not in {"127.0.0.1", "localhost"}:
            return error_response(Fault("HOST_NOT_ALLOWED", "请求主机不受信任。", 403))
        origin = request.headers.get("origin")
        if origin is not None and origin not in settings.allowed_origins:
            return error_response(Fault("ORIGIN_NOT_ALLOWED", "此来源不能访问本机服务。", 403))
        if request.url.path != "/health":
            authorization = request.headers.get("authorization", "")
            if not hmac.compare_digest(authorization, f"Bearer {settings.token}"):
                return error_response(Fault("UNAUTHORIZED", "本机会话认证失败。", 401))
        if request.method == "OPTIONS":
            return error_response(Fault("METHOD_NOT_ALLOWED", "请通过桌面宿主或受保护开发代理访问。", 405))
        host_action = bool(re.fullmatch(r"/api/v1/restores/[^/]+/activation", request.url.path)) or request.url.path.startswith('/api/v1/host/')
        if host_action and (not settings.host_token or not hmac.compare_digest(request.headers.get("x-ailab-host-token", ""), settings.host_token)):
            return error_response(Fault("HOST_AUTH_REQUIRED", "切换工作库只能由桌面宿主发起。", 403))
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 2 * 1024 * 1024:
                return error_response(Fault("REQUEST_TOO_LARGE", "请求正文超过 2 MiB。", 413))
        request._body = bytes(body)
        writing = request.method not in {"GET", "HEAD"} or request.url.path == '/api/v1/market/catalog'
        if writing:
            with service.store.lock:
                if service.activation_pending and time.monotonic() >= service.activation_deadline:
                    service.activation_pending = False
                if service.activation_pending and not (host_action and request.method == "DELETE"):
                    return error_response(Fault("LIBRARY_SWITCH_PENDING", "正在切换工作库，请等待桌面宿主完成后再操作。", 409))
                if service.maintenance_pending:
                    return error_response(Fault("CLEANUP_BUSY", "正在备份、整理或恢复缓存，请等待本次操作完成。", 409))
                service.active_writes += 1
        try:
            return await call_next(request)
        except Exception:
            return error_response(Fault("INTERNAL_ERROR", "服务未完成本次请求，请查看本机日志或重试。", 500))
        finally:
            if writing:
                with service.store.lock:
                    service.active_writes -= 1

    @app.exception_handler(Fault)
    async def fault_handler(request, error):
        return error_response(error)

    @app.exception_handler(RequestValidationError)
    async def invalid_handler(request, error):
        fields = [{"field": ".".join(str(x) for x in issue["loc"]), "type": issue["type"]} for issue in error.errors()]
        return error_response(Fault("INVALID_CONFIG", "字段类型、数值范围或请求结构不正确。", 422, fields=fields))

    @app.exception_handler(HTTPException)
    async def http_handler(request, error):
        return error_response(Fault("RESOURCE_NOT_FOUND" if error.status_code == 404 else "METHOD_NOT_ALLOWED", "接口不存在或不支持此操作。", error.status_code))

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.post("/api/v1/cleanup-plans")
    def cleanup_plan(payload: EmptyInput):
        return service.cleanup.plan(payload.model_dump())

    @app.post("/api/v1/cleanups")
    def cleanup_execute(payload: CleanupInput, idempotency_key: str | None = Header(default=None)):
        return service.cleanup.execute(payload.model_dump(), idempotency_key)

    @app.get("/api/v1/cleanups")
    def cleanups():
        return service.cleanup.list_items()

    @app.get("/api/v1/cleanups/{cleanup_id}")
    def cleanup(cleanup_id: str):
        return service.cleanup.get(cleanup_id)

    @app.post("/api/v1/cleanups/{cleanup_id}/restore")
    def cleanup_restore(cleanup_id: str, payload: EmptyInput, idempotency_key: str | None = Header(default=None)):
        return service.cleanup.restore(cleanup_id, payload.model_dump(), idempotency_key)

    @app.post("/api/v1/projects")
    def create_project(payload: ProjectInput):
        return service.project(payload.model_dump())

    @app.patch("/api/v1/projects/{project_id}")
    def edit_project(project_id: str, payload: ProjectEdit):
        with service.store.transaction():
            project = service.store.get("project", project_id)
            if project["revision"] != payload.expected_revision:
                raise Fault("REVISION_CONFLICT", "项目已更新，请刷新。", 409, current_revision=project["revision"])
            project.update(name=payload.name, revision=project["revision"] + 1)
            service.store.put("project", project)
            return project

    def attempt_summary(item):
        fields = {"id", "resource_type", "task_id", "project_id", "created_at", "state", "state_version", "collection_version",
                  "compute_outcome", "collection_state", "recovery_required", "phase", "progress", "last_event_sequence",
                  "checkpoint_id", "terminal_reason", "stop_status", "connection_state", "executor_type"}
        return {**{key: value for key, value in item.items() if key in fields}, "allowed_actions": service.actions(item)}

    def task_summary(item):
        fields = {"id", "resource_type", "project_id", "name", "kind", "operation", "created_at", "workflow_ref", "export_id", "immutable_draft", "draft_revision"}
        page = service.store.page("attempt", item["project_id"], limit=1, task_id=item["id"], descending=True)
        return {**{key: value for key, value in item.items() if key in fields},
                "latest_attempt": attempt_summary(page["items"][0]) if page["items"] else None}

    def listing(kind, project_id, cursor, limit, descending=False):
        page = service.store.page(kind, project_id, cursor, limit, descending=descending)
        return {**page, "items": [(task_summary(item) if kind == "task" else service.public(item)) for item in page["items"]]}

    @app.get("/api/v1/projects")
    def projects(cursor: str | None = None, limit: int = Query(default=100, ge=1, le=200)):
        return listing("project", None, cursor, limit)

    @app.get('/api/v1/projects/{project_id}')
    def project_detail(project_id: str):
        return service.public(service.store.get('project', project_id))

    @app.post('/api/v1/datasets/split-plans', status_code=202)
    def dataset_split_prepare(payload: DatasetSplitPrepare, idempotency_key: str | None = Header(default=None)):
        return service.dataset_splits.prepare(payload.model_dump(), idempotency_key)

    @app.get('/api/v1/datasets/split-plans/{plan_id}')
    def dataset_split_plan(plan_id: str):
        return service.dataset_splits.get(plan_id)

    @app.get('/api/v1/datasets/split-plans')
    def dataset_split_plans(project_id: str = Query(min_length=1, max_length=100), source_dataset_id: str | None = None, cursor: str | None = None, limit: int = Query(default=100, ge=1, le=200)):
        return service.dataset_splits.plans(project_id, source_dataset_id, cursor, limit)

    @app.post('/api/v1/datasets/split-plans/{plan_id}/cancel')
    def dataset_split_cancel(plan_id: str, payload: EmptyInput, idempotency_key: str | None = Header(default=None)):
        return service.dataset_splits.cancel(plan_id, idempotency_key)

    @app.post('/api/v1/datasets/splits')
    def dataset_split_apply(payload: DatasetSplitApply, idempotency_key: str | None = Header(default=None)):
        return service.dataset_splits.apply(payload.model_dump(), idempotency_key)

    @app.get('/api/v1/datasets/splits')
    def dataset_splits(project_id: str | None = None, cursor: str | None = None, limit: int = Query(default=100, ge=1, le=200)):
        return listing('dataset-split', project_id, cursor, limit)

    @app.get('/api/v1/datasets/splits/{split_id}')
    def dataset_split_detail(split_id: str):
        return service.public(service.store.get('dataset-split', split_id))

    @app.get('/api/v1/datasets/{dataset_id}')
    def dataset_detail(dataset_id: str):
        return service.public(service.store.get('dataset', dataset_id))

    @app.get('/api/v1/materials/{material_id}')
    def material_detail(material_id: str):
        return service.public(service.store.get('material', material_id))

    @app.get('/api/v1/evaluation-plans/{plan_id}')
    def evaluation_plan_detail(plan_id: str):
        return service.public(service.store.get('evaluation-plan', plan_id))

    @app.get("/api/v1/models")
    def models(project_id: str | None = None, cursor: str | None = None, limit: int = Query(default=100, ge=1, le=200)):
        return listing("model", project_id, cursor, limit)

    @app.get("/api/v1/datasets")
    def datasets(project_id: str | None = None, cursor: str | None = None, limit: int = Query(default=100, ge=1, le=200)):
        return listing("dataset", project_id, cursor, limit)

    @app.get('/api/v1/materials')
    def materials(project_id: str | None = None, cursor: str | None = None, limit: int = Query(default=100, ge=1, le=200)):
        return listing('material', project_id, cursor, limit)

    @app.get("/api/v1/adapters")
    def adapters(project_id: str | None = None, cursor: str | None = None, limit: int = Query(default=100, ge=1, le=200)):
        return listing("adapter", project_id, cursor, limit)

    @app.get("/api/v1/adapters/{adapter_id}")
    def adapter(adapter_id: str):
        return service.public(service.store.get("adapter", adapter_id))

    @app.post("/api/v1/attempts/{attempt_id}/adapters")
    def save_adapter(attempt_id: str, payload: AdapterInput, idempotency_key: str | None = Header(default=None)):
        return service.delivery.save_adapter(attempt_id, payload.model_dump(), idempotency_key)

    @app.post("/api/v1/conversions")
    def conversion_task(payload: ConversionInput, idempotency_key: str | None = Header(default=None)):
        return service.conversion.new_task(payload.model_dump(), idempotency_key)

    @app.post("/api/v1/attempts/{attempt_id}/converted-models")
    def converted_model(attempt_id: str, payload: AdapterInput, idempotency_key: str | None = Header(default=None)):
        return service.conversion.save_model(attempt_id, payload.model_dump(), idempotency_key)

    @app.get("/api/v1/tasks")
    def tasks(project_id: str | None = None, cursor: str | None = None, limit: int = Query(default=100, ge=1, le=200)):
        return listing("task", project_id, cursor, limit, descending=True)

    @app.get("/api/v1/works")
    def works(project_id: str | None = None, cursor: str | None = None, limit: int = Query(default=100, ge=1, le=200)):
        return listing("work", project_id, cursor, limit, descending=True)

    @app.get('/api/v1/workflow-runs')
    def workflow_runs(project_id: str | None = None, cursor: str | None = None, limit: int = Query(default=100, ge=1, le=200)):
        return listing('workflow-run', project_id, cursor, limit, descending=True)

    @app.post('/api/v1/workflow-runs')
    def workflow_start(payload: WorkflowStart, idempotency_key: str | None = Header(default=None)):
        return service.workflows.start(payload.model_dump(), idempotency_key)

    @app.get('/api/v1/workflow-runs/{run_id}')
    def workflow_run(run_id: str):
        return service.workflows.get(run_id)

    @app.patch('/api/v1/workflow-runs/{run_id}/steps/{step_id}/input')
    def workflow_input(run_id: str, step_id: Literal['image', 'video', 'audio'], payload: WorkflowInputEdit, idempotency_key: str | None = Header(default=None)):
        return service.workflows.revise_input(run_id, step_id, payload.model_dump(), idempotency_key)

    @app.post('/api/v1/workflow-runs/{run_id}/advance')
    def workflow_advance(run_id: str, payload: WorkflowAdvance, idempotency_key: str | None = Header(default=None)):
        return service.workflows.advance(run_id, payload.model_dump(), idempotency_key)

    @app.post('/api/v1/workflow-runs/{run_id}/reuse-output')
    def workflow_reuse(run_id: str, payload: WorkflowReuse, idempotency_key: str | None = Header(default=None)):
        return service.workflows.reuse_output(run_id, payload.model_dump(), idempotency_key)

    @app.post('/api/v1/workflow-runs/{run_id}/save')
    def workflow_save(run_id: str, payload: WorkflowSave, idempotency_key: str | None = Header(default=None)):
        return service.workflows.save_result(run_id, payload.model_dump(exclude_none=True), idempotency_key)

    @app.get('/api/v1/workflow-results')
    def workflow_results(project_id: str | None = None, cursor: str | None = None, limit: int = Query(default=100, ge=1, le=200)):
        return listing('workflow-result', project_id, cursor, limit)

    @app.get('/api/v1/workflow-results/{result_id}')
    def workflow_result(result_id: str):
        return service.public(service.store.get('workflow-result', result_id))

    @app.post("/api/v1/import-grants")
    def import_grant(payload: GrantInput):
        return service.grant(payload.path)

    @app.post("/api/v1/export-grants")
    def export_grant(payload: GrantInput):
        return service.delivery.export_grant(payload.path)

    @app.post("/api/v1/exports/prepare")
    def export_prepare(payload: ExportPlanInput):
        return service.delivery.prepare_export(payload.model_dump())

    @app.post("/api/v1/exports")
    def export_start(payload: ExportInput, idempotency_key: str | None = Header(default=None)):
        return service.delivery.start_export(payload.model_dump(), idempotency_key)

    @app.get("/api/v1/exports")
    def exports(project_id: str | None = None, cursor: str | None = None, limit: int = Query(default=100, ge=1, le=200)):
        page = service.store.page("export", project_id, cursor, limit)
        return {**page, "items": [service.delivery.export_record(record) for record in page["items"]]}

    @app.get("/api/v1/exports/{export_id}")
    def export(export_id: str):
        return service.delivery.export_record(service.store.get("export", export_id))

    @app.post("/api/v1/evaluation-plans")
    def evaluation_plan(payload: EvaluationPlanInput, idempotency_key: str | None = Header(default=None)):
        return service.evaluation.create_plan(payload.model_dump(), idempotency_key)

    @app.get("/api/v1/evaluation-plans")
    def evaluation_plans(project_id: str | None = None, cursor: str | None = None, limit: int = Query(default=100, ge=1, le=200)):
        return listing("evaluation-plan", project_id, cursor, limit)

    @app.post("/api/v1/evaluations")
    def evaluation_task(payload: EvaluationInput, idempotency_key: str | None = Header(default=None)):
        return service.evaluation.new_task(payload.model_dump(), idempotency_key)

    @app.get("/api/v1/evaluations")
    def evaluations(project_id: str | None = None, cursor: str | None = None, limit: int = Query(default=20, ge=1, le=100)):
        page = service.store.page("attempt", project_id, cursor, limit, operation="evaluate")
        return {**page, "items": [service.evaluation.record(item, detailed=False) for item in page["items"]]}

    @app.get("/api/v1/evaluations/{evaluation_id}")
    def evaluation(evaluation_id: str):
        return service.evaluation.record(service.store.get("attempt", evaluation_id))

    @app.get("/api/v1/candidates")
    def candidates(project_id: str | None = None, cursor: str | None = None, limit: int = Query(default=100, ge=1, le=200)):
        return listing("candidate", project_id, cursor, limit)

    @app.post("/api/v1/candidates/{candidate_id}/register")
    def candidate_register(candidate_id: str, payload: CandidateRegistration, idempotency_key: str | None = Header(default=None)):
        return service.evaluation.register(candidate_id, payload.model_dump(), idempotency_key)

    @app.post("/api/v1/models/import-plans")
    def model_plan(payload: ImportPlanInput):
        return service.import_plan("model", payload.model_dump(by_alias=True))

    @app.post("/api/v1/datasets/import-plans")
    def dataset_plan(payload: ImportPlanInput):
        return service.import_plan("dataset", payload.model_dump(by_alias=True))

    @app.post("/api/v1/models/imports")
    def model_import(payload: ImportInput, idempotency_key: str | None = Header(default=None)):
        return service.import_asset("model", payload.model_dump(), idempotency_key)

    @app.post("/api/v1/datasets/imports")
    def dataset_import(payload: ImportInput, idempotency_key: str | None = Header(default=None)):
        return service.import_asset("dataset", payload.model_dump(), idempotency_key)

    @app.post('/api/v1/materials/import-plans')
    def material_plan(payload: ImportPlanInput):
        return service.import_plan('material', payload.model_dump(by_alias=True))

    @app.post('/api/v1/materials/imports')
    def material_import(payload: ImportInput, idempotency_key: str | None = Header(default=None)):
        return service.import_asset('material', payload.model_dump(), idempotency_key)

    @app.post("/api/v1/tasks")
    def create_task(payload: TaskInput):
        return service.new_task(payload.model_dump())

    @app.get("/api/v1/tasks/{task_id}")
    def task(task_id: str):
        item = service.store.get("task", task_id)
        page = service.store.page("attempt", item["project_id"], limit=100, task_id=item["id"], descending=True)
        attempts = [attempt_summary(attempt) for attempt in page["items"]]
        return {**service.public(item), "attempts": attempts, "attempts_next_cursor": page["next_cursor"], "latest_attempt": attempts[0] if attempts else None}

    @app.patch("/api/v1/tasks/{task_id}/draft")
    def draft(task_id: str, payload: DraftEdit):
        return service.save_draft(task_id, payload.model_dump())

    @app.post("/api/v1/tasks/{task_id}/preflight")
    def preflight(task_id: str, payload: PreflightInput):
        return service.preflight(task_id, payload.draft_revision)

    @app.post("/api/v1/tasks/{task_id}/attempts")
    def submit(task_id: str, payload: SubmitInput, idempotency_key: str | None = Header(default=None)):
        return service.submit(task_id, payload.model_dump(), idempotency_key)

    @app.get("/api/v1/attempts")
    def attempts(project_id: str | None = None, task_id: str | None = None, cursor: str | None = None, limit: int = Query(default=100, ge=1, le=200)):
        page = service.store.page("attempt", project_id, cursor, limit, task_id=task_id, descending=True)
        return {**page, "items": [attempt_summary(item) for item in page["items"]]}

    @app.get("/api/v1/attempts/{attempt_id}")
    def attempt(attempt_id: str):
        return service.public(service.store.get("attempt", attempt_id))

    @app.get("/api/v1/attempts/{attempt_id}/events")
    def events(attempt_id: str, request: Request, after: int = Query(default=0, ge=0), limit: int = Query(default=200, ge=1, le=1000), format: Literal["json", "sse"] = "json"):
        if format == "json":
            return service.store.events(attempt_id, after, limit)
        cursor = request.headers.get("last-event-id")
        if cursor:
            if not cursor.isdigit():
                raise Fault("INVALID_CURSOR", "事件游标必须是非负整数。")
            after = int(cursor)
        service.store.get("attempt", attempt_id)

        async def stream():
            nonlocal after
            while not await request.is_disconnected():
                page = service.store.events(attempt_id, after, limit)
                for event in page["items"]:
                    after = event["sequence"]
                    yield f"id: {after}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
                state = service.store.get("attempt", attempt_id)
                if state["state"] in {"succeeded", "failed", "cancelled"} and after >= state["last_event_sequence"]:
                    break
                yield ": heartbeat\n\n"
                await asyncio.sleep(1)
        return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-store"})

    @app.post("/api/v1/attempts/{attempt_id}/cancel")
    def cancel(attempt_id: str, payload: ControlInput, idempotency_key: str | None = Header(default=None)):
        return service.control(attempt_id, payload.model_dump(), idempotency_key)

    @app.post("/api/v1/attempts/{attempt_id}/force-stop")
    def force_stop(attempt_id: str, payload: ControlInput, idempotency_key: str | None = Header(default=None)):
        return service.control(attempt_id, payload.model_dump(), idempotency_key, force=True)

    @app.post("/api/v1/attempts/{attempt_id}/reconcile")
    def reconcile(attempt_id: str, payload: ControlInput, idempotency_key: str | None = Header(default=None)):
        return service.reconcile(attempt_id, payload.model_dump(), idempotency_key)

    @app.post("/api/v1/attempts/{attempt_id}/pause")
    def pause(attempt_id: str, payload: ControlInput | None = None, idempotency_key: str | None = Header(default=None)):
        if payload is None:
            service.store.get("attempt", attempt_id)
            raise Fault("CONTROL_NOT_SUPPORTED", "安全暂停需要当前训练运行版本。", 409)
        return service.checkpoints.command(attempt_id, payload.model_dump(), idempotency_key, "pause")

    @app.post("/api/v1/attempts/{attempt_id}/resume")
    def resume(attempt_id: str, payload: ControlInput | None = None, idempotency_key: str | None = Header(default=None)):
        if payload is None:
            service.store.get("attempt", attempt_id)
            raise Fault("CONTROL_NOT_SUPPORTED", "安全继续需要当前训练运行版本。", 409)
        return service.checkpoints.command(attempt_id, payload.model_dump(), idempotency_key, "resume")

    @app.get("/api/v1/checkpoints")
    def checkpoints(project_id: str | None = None, attempt_id: str | None = None):
        if attempt_id:
            service.store.get("attempt", attempt_id)
        return {"items": [service.public(item) for item in service.store.list("checkpoint", project_id) if not attempt_id or item["source_attempt_id"] == attempt_id]}

    @app.get("/api/v1/checkpoints/{checkpoint_id}")
    def checkpoint(checkpoint_id: str):
        return service.public(service.store.get("checkpoint", checkpoint_id))

    @app.post("/api/v1/checkpoints/{checkpoint_id}/restore-task")
    def checkpoint_task(checkpoint_id: str, payload: CheckpointTaskInput, idempotency_key: str | None = Header(default=None)):
        return service.checkpoints.new_task(checkpoint_id, payload.model_dump(), idempotency_key)

    @app.post("/api/v1/attempts/{attempt_id}/collections")
    def collect(attempt_id: str, payload: CollectionInput, idempotency_key: str | None = Header(default=None)):
        return service.collect(attempt_id, payload.model_dump(), idempotency_key)

    @app.get("/api/v1/collections/{collection_id}")
    def collection(collection_id: str):
        return service.public(service.store.get("collection", collection_id))

    @app.post("/api/v1/works")
    def save_work(payload: WorkInput, idempotency_key: str | None = Header(default=None)):
        return service.save_work(payload.model_dump(), idempotency_key)

    @app.get("/api/v1/works/{work_id}")
    def work(work_id: str):
        return service.public(service.store.get("work", work_id))

    @app.get('/api/v1/works/{work_id}/recipe')
    def work_recipe(work_id: str, project_id: str = Query(min_length=1)):
        return service.work_recipes.view(work_id, project_id)

    @app.post('/api/v1/works/{work_id}/reuse-task')
    def reuse_work_recipe(work_id: str, payload: WorkReuseInput, idempotency_key: str | None = Header(default=None)):
        return service.work_recipes.reuse(work_id, payload.model_dump(), idempotency_key)

    @app.patch('/api/v1/works/{work_id}/favorite')
    def favorite_work(work_id: str, payload: WorkFavoriteInput):
        return service.work_recipes.favorite(work_id, payload.model_dump())

    @app.get('/api/v1/works/{work_id}/revisions')
    def work_revisions(work_id: str, limit: int = Query(default=100, ge=1, le=100), before_revision: int | None = Query(default=None, ge=1)):
        return service.work_revisions.view(work_id, limit, before_revision)

    @app.post('/api/v1/works/{work_id}/revisions')
    def create_work_revision(work_id: str, payload: WorkRevisionInput, idempotency_key: str | None = Header(default=None)):
        return service.work_revisions.create(work_id, payload.model_dump(), idempotency_key)

    @app.post('/api/v1/works/{work_id}/materials')
    def work_material(work_id: str, payload: EmptyInput, idempotency_key: str | None = Header(default=None)):
        return service.media.material_from_work(work_id, idempotency_key)

    @app.get('/api/v1/artifacts/{artifact_id}/content')
    def artifact_content(artifact_id: str):
        raw, media_type = service.media.content(artifact_id)
        return Response(raw, media_type=media_type, headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})

    @app.post('/api/v1/remote-transfers/prepare')
    def remote_transfer_prepare(payload: RemoteTransferPrepare):
        return service.remote_execution.transfer_prepare(payload.model_dump())

    @app.post('/api/v1/remote-transfers')
    def remote_transfer_submit(payload: RemoteTransferSubmit, idempotency_key: str | None = Header(default=None)):
        return service.remote_execution.transfer_submit(payload.model_dump(), idempotency_key)

    @app.get('/api/v1/remote-transfers')
    def remote_transfers(project_id: str | None = None, cursor: str | None = None, limit: int = Query(default=100, ge=1, le=100), execution_target_id: str | None = None):
        return service.remote_execution.listing(project_id, cursor, limit, execution_target_id)

    @app.get('/api/v1/projects/{project_id}/execution-default')
    def execution_default(project_id: str):
        return service.execution_default(project_id)

    @app.post('/api/v1/projects/{project_id}/execution-default')
    def save_execution_default(project_id: str, payload: ExecutionDefaultInput):
        return service.execution_default(project_id, payload.model_dump())

    @app.get("/api/v1/devices")
    def devices():
        import platform
        environment = service.environment(origin='devices')
        return {"items": [{"id": "apple-gpu", "name": "本机 Apple GPU", "location": "local", "connected": True,
                           "platform": platform.system(), "architecture": platform.machine(), "ready": environment["ready"],
                           "status": "ready" if environment["ready"] else "not_prepared", "reason": environment["reason"], "environment": environment}]}

    @app.get('/api/v1/execution-targets')
    def execution_targets(project_id: str | None = None):
        return service.execution_targets.listing(project_id)

    @app.get('/api/v1/execution-targets/{target_id}')
    def execution_target(target_id: str):
        return service.execution_targets.get(target_id)

    @app.post('/api/v1/execution-targets')
    def create_execution_target(payload: ExecutionTargetInput, idempotency_key: str | None = Header(default=None)):
        return service.execution_targets.create(payload.model_dump(), idempotency_key)

    @app.post('/api/v1/host/execution-targets')
    def create_host_execution_target(payload: HostExecutionTargetInput, idempotency_key: str | None = Header(default=None)):
        return service.execution_targets.create(payload.model_dump(), idempotency_key, host=True)

    @app.post('/api/v1/execution-targets/{target_id}/credentials')
    def execution_credentials(target_id: str, payload: ExecutionCredentialInput):
        return service.execution_targets.credentials(target_id, payload.model_dump())

    @app.post('/api/v1/host/execution-targets/{target_id}/credentials')
    def host_execution_credentials(target_id: str, payload: HostExecutionCredentialInput, idempotency_key: str | None = Header(default=None)):
        return service.execution_targets.credentials(target_id, payload.model_dump(), host=True, key=idempotency_key)

    @app.delete('/api/v1/host/execution-targets/{target_id}/credentials')
    def delete_execution_credentials(target_id: str, payload: ExecutionCredentialDelete, idempotency_key: str | None = Header(default=None)):
        return service.execution_targets.credentials(target_id, payload.model_dump(), host=True, forget=True, key=idempotency_key)

    @app.post('/api/v1/host/execution-targets/{target_id}/credentials/cleanup')
    def cleanup_execution_credentials(target_id: str, payload: ExecutionCredentialCleanup, idempotency_key: str | None = Header(default=None)):
        return service.execution_targets.cleanup_credentials(target_id, payload.model_dump(), idempotency_key)

    @app.post('/api/v1/execution-targets/{target_id}/check')
    def check_execution_target(target_id: str, payload: EmptyInput):
        return service.execution_targets.check(target_id)

    @app.get('/api/v1/training-contracts')
    def list_training_contracts():
        return {'items': training_contracts()}

    @app.get("/api/v1/capabilities")
    def capabilities(refresh: bool = False):
        # 三个独立环境并行探测；图片与视频使用同一运行时。
        with ThreadPoolExecutor(max_workers=3) as probes:
            text_probe = probes.submit(service.environment, refresh=refresh, origin='capabilities')
            image_probe = probes.submit(service.media.environment, 'image', refresh=refresh, origin='capabilities')
            audio_probe = probes.submit(service.media.environment, 'audio', refresh=refresh, origin='capabilities')
            environment = text_probe.result()
            media_profiles = {'image': image_probe.result(), 'audio': audio_probe.result()}
            media_profiles['video'] = media_profiles['image']
        checkpoints_ready = environment["ready"] and service.checkpoints.supported({"snapshot": {"operation": "train", "runtime": {}, "environment": environment}})
        items = [{"kind": kind, "operation": operation, "engine": "mlx" if kind == "text" else None,
                           "device_id": "apple-gpu", "supported": kind == "text" and environment["ready"],
                           "status": "available" if kind == "text" and environment["ready"] else "not_prepared" if kind == "text" else "not_supported",
                           "reason": environment["reason"] if kind == "text" else "此适配器尚未接入，当前不能运行。",
                           "model_constraint": "Qwen2.5-0.5B-Instruct；MLX 4-bit／64／affine 仅开放独立生成", "pause": kind == "text" and operation == "train" and checkpoints_ready, "cancel": True}
                          for kind in ('text',) for operation in ("generate", "train")]
        items[0]['generation_parameters'] = {
            'context_limit': {'default': 4096, 'minimum': 128, 'maximum': 4096, 'unit': 'token', 'scope': '模板、输入与最大输出合计'},
            'overflow': {'default': 'reject', 'supported': ['reject'], 'reason': '当前单条输入没有可裁剪的旧对话；超限时拒绝，不修改输入。'},
            'stop': {'default': [], 'maximum_items': 8, 'maximum_characters_per_item': 128, 'scope': '字符串精确匹配，空格保留，跨块匹配，命中时停止模型生成'},
            'stream': {'default': True, 'scope': '控制 token 增量事件；阶段、取消与最终结果保存始终可用'},
            'thinking': {'default': 'default', 'supported': ['default'], 'switch_supported': False, 'reason': 'Qwen2.5 模型与模板没有思考切换能力，不以隐藏输出冒充关闭思考。'},
        }
        items[1]['training_contract'] = training_contracts()[0]
        from .media import DEFAULTS
        for kind in ('image', 'video', 'audio'):
            media_environment = media_profiles[kind]
            for operation in ('generate', 'train'):
                supported = (kind, operation) in DEFAULTS
                ready = supported and media_environment['ready']
                items.append({'kind': kind, 'operation': operation, 'engine': media_environment['engine'], 'device_id': media_environment['device_id'], 'supported': ready, 'status': 'available' if ready else 'not_prepared' if supported else 'not_supported', 'reason': '' if ready else media_environment['reason'] if supported else '当前尚未接入此真实训练组合。', 'model_constraint': {'image': '固定 segmind/tiny-sd；512 像素生成与 12 步实验 LoRA', 'video': '固定 SVD；14 帧图生视频', 'audio': '固定 Kokoro 中文小北音色；CPU 24 kHz'}[kind], 'pause': False, 'cancel': supported})
        return {'items': items}

    @app.post("/api/v1/backups")
    def backup(idempotency_key: str | None = Header(default=None)):
        return service.backup(idempotency_key)

    @app.get("/api/v1/backups")
    def backups():
        return service.backup_manager.list_backups()

    @app.post("/api/v1/restore-plans")
    def restore_plan(payload: RestorePlanInput):
        return service.backup_manager.plan(payload.model_dump())

    @app.post("/api/v1/restores")
    def restore(payload: RestoreInput, idempotency_key: str | None = Header(default=None)):
        return service.backup_manager.restore(payload.model_dump(), idempotency_key)

    @app.get("/api/v1/restores")
    def restores():
        return service.backup_manager.list_restores()

    @app.get("/api/v1/restores/{restore_id}")
    def restored(restore_id: str):
        return service.backup_manager.get_restore(restore_id)

    @app.post("/api/v1/restores/{restore_id}/activation")
    def activate_restored(restore_id: str):
        return service.backup_manager.activate(restore_id)

    @app.delete("/api/v1/restores/{restore_id}/activation")
    def cancel_activation(restore_id: str):
        return service.backup_manager.cancel_activation()

    @app.get("/api/v1/settings")
    def settings_get():
        return service.get_settings()

    @app.get("/api/v1/ui-context")
    def ui_context_get():
        return service.get_ui_context()

    @app.patch("/api/v1/ui-context")
    def ui_context_update(payload: UIContextPatch):
        return service.update_ui_context(payload.model_dump(exclude_unset=True))

    @app.patch("/api/v1/settings")
    def settings_update(payload: SettingsInput):
        return service.update_settings(payload.model_dump(exclude_unset=True))

    @app.post('/api/v1/ai/requests')
    def ai_request(payload: AIRequestInput, idempotency_key: str | None = Header(default=None)):
        return service.ai.new_request(payload.model_dump(), idempotency_key)

    @app.get('/api/v1/ai/requests')
    def ai_requests(target_task_id: str, limit: int = Query(default=20, ge=1, le=100)):
        target = service.store.get('task', target_task_id)
        values = [value for value in service.store.list('ai-request', target['project_id']) if value['target_task_id'] == target_task_id]
        return {'items': [service.ai.public_request(value) for value in values[-limit:]]}

    @app.get('/api/v1/ai/requests/{request_id}')
    def ai_request_get(request_id: str):
        return service.ai.public_request(service.store.get('ai-request', request_id))

    @app.post('/api/v1/ai/requests/{request_id}/proposals')
    def ai_proposal_parse(request_id: str, payload: AIResponseInput, idempotency_key: str | None = Header(default=None)):
        return service.ai.from_attempt(request_id, payload.model_dump(), idempotency_key)

    @app.get('/api/v1/ai/proposals/{proposal_id}')
    def ai_proposal_get(proposal_id: str):
        return service.store.get('ai-proposal', proposal_id)

    @app.post('/api/v1/ai/proposals/{proposal_id}/apply')
    def ai_apply(proposal_id: str, payload: AIRevisionInput, idempotency_key: str | None = Header(default=None)):
        return service.ai.apply(proposal_id, payload.model_dump(), idempotency_key)

    @app.post('/api/v1/ai/proposals/{proposal_id}/undo')
    def ai_undo(proposal_id: str, payload: AIRevisionInput, idempotency_key: str | None = Header(default=None)):
        return service.ai.apply(proposal_id, payload.model_dump(), idempotency_key, undo=True)

    @app.get('/api/v1/models/{model_id}')
    def get_model(model_id: str):
        return service.public(service.store.get('model', model_id))

    @app.get('/api/v1/model-catalog')
    def model_catalog():
        return {'items': [service.model_downloads.catalog()]}

    @app.post('/api/v1/diagnostics/previews')
    def diagnostic_preview(payload: DiagnosticPreviewInput):
        return service.diagnostics.preview(payload.model_dump())

    @app.get('/api/v1/diagnostics/previews/{preview_id}')
    def diagnostic_get(preview_id: str):
        return service.diagnostics.get(preview_id)

    @app.post('/api/v1/diagnostics/previews/{preview_id}/cancel')
    def diagnostic_cancel(preview_id: str, payload: EmptyInput, idempotency_key: str | None = Header(default=None)):
        return service.diagnostics.cancel(preview_id, idempotency_key)

    @app.post('/api/v1/diagnostics/exports')
    def diagnostic_export(payload: DiagnosticExportInput, idempotency_key: str | None = Header(default=None)):
        return service.diagnostics.export(payload.model_dump(), idempotency_key)

    @app.get('/api/v1/model-downloads')
    def model_download_list(project_id: str):
        service.store.get('project', project_id)
        return {'items': service.store.list('model-download', project_id)}

    @app.post('/api/v1/model-downloads')
    def start_model_download(payload: ModelDownloadInput, idempotency_key: str | None = Header(default=None)):
        return service.model_downloads.start(payload.model_dump(), idempotency_key)

    @app.get('/api/v1/model-downloads/{download_id}')
    def get_model_download(download_id: str):
        return service.model_downloads.get(download_id)

    @app.post('/api/v1/model-downloads/{download_id}/resume')
    def resume_model_download(download_id: str, payload: EmptyInput, idempotency_key: str | None = Header(default=None)):
        return service.model_downloads.resume(download_id, idempotency_key)

    @app.post('/api/v1/model-downloads/{download_id}/cancel')
    def cancel_model_download(download_id: str, payload: EmptyInput, idempotency_key: str | None = Header(default=None)):
        return service.model_downloads.cancel(download_id, idempotency_key)

    @app.post('/api/v1/model-downloads/{download_id}/models')
    def register_model_download(download_id: str, payload: EmptyInput, idempotency_key: str | None = Header(default=None)):
        return service.model_downloads.register(download_id, idempotency_key)

    @app.post('/api/v1/host/reconfiguration')
    def begin_host_reconfiguration(payload: EmptyInput):
        with service.store.lock:
            active = [item for item in service.store.list('attempt') if item['state'] not in {'succeeded', 'failed', 'cancelled'} or item.get('recovery_required')]
            downloads = [item for kind in ('market-download', 'model-download') for item in service.store.list(kind) if item['state'] in {'queued', 'downloading', 'verifying'}]
            if service.closed.is_set() or service.active_writes != 1 or service.activation_pending or service.maintenance_pending or active or downloads or service.threads or service.dataset_splits.unresolved():
                raise Fault('HOST_RECONFIGURATION_BUSY', '请先完成当前运行、下载、导出或保存，再修改数据来源。', 409)
            service.activation_pending = True
            service.activation_deadline = time.monotonic() + 30
            return {'ready': True, 'lease_seconds': 30}

    @app.delete('/api/v1/host/reconfiguration')
    def cancel_host_reconfiguration(payload: EmptyInput):
        with service.store.lock:
            service.activation_pending = False
            service.activation_deadline = 0
            return {'released': True}

    from .market_api import mount_market
    mount_market(app, service)
    return app
