"""Public request contracts shared by standalone and desktop-mounted APIs."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class Paths(Strict):
    models: str = Field(default='', max_length=4096)
    datasets: str = Field(default='', max_length=4096)


class Install(Strict):
    accelerator: Literal['cpu', 'cuda', 'metal'] = 'cpu'


class Settings(Strict):
    max_concurrent_tasks: int = Field(default=1, ge=1, le=16)


class EnvironmentPath(Strict):
    path: str = Field(default='', max_length=4096)


class ModelCheck(Strict):
    model: str


class ModelCapabilities(ModelCheck):
    engine: Literal['llama', 'vllm']
    vision_handler: Literal['none', 'llava15', 'llava16', 'moondream'] = 'none'
    mmproj: str = ''


class MaterialImport(Strict):
    path: str = ''
    name: str = Field(default='', max_length=255)
    data: str | None = Field(default=None, max_length=1500000)


class UploadStart(Strict):
    name: str = Field(min_length=1, max_length=255)
    size: int = Field(gt=0, le=2 * 1024**3)


class UploadChunk(Strict):
    offset: int = Field(ge=0)
    data: str = Field(max_length=1500000)


class SFT(Strict):
    model: str
    dataset: str
    trust_remote_code: bool = False
    method: Literal['lora', 'full'] = 'lora'
    device: Literal['auto', 'cpu', 'cuda', 'mps'] = 'auto'
    epochs: float = Field(default=1, gt=0, le=100)
    max_steps: int = Field(default=-1, ge=-1, le=1000000)
    learning_rate: float = Field(default=0.0002, gt=0, le=0.1)
    batch_size: int = Field(default=1, ge=1, le=128)
    gradient_accumulation: int = Field(default=8, ge=1, le=1024)
    max_length: int = Field(default=2048, ge=32, le=131072)
    lora_rank: int = Field(default=16, ge=1, le=512)
    lora_alpha: int = Field(default=32, ge=1, le=1024)
    lora_dropout: float = Field(default=0.05, ge=0, lt=1)
    target_modules: str = 'all-linear'
    precision: Literal['auto', 'float32', 'float16', 'bfloat16'] = 'auto'
    validation_fraction: float = Field(default=0.1, ge=0, lt=0.5)
    logging_steps: int = Field(default=1, ge=1, le=1000)
    save_steps: int = Field(default=100, ge=1, le=100000)
    seed: int = Field(default=42, ge=0, le=2147483647)
    gradient_checkpointing: bool = True
    text_column: str = 'text'
    loss_scope: Literal['assistant', 'all'] = 'assistant'

    @model_validator(mode='after')
    def steps(self):
        if self.max_steps == 0:
            raise ValueError('最大步数应为 -1（按轮数）或正整数')
        return self


class Message(Strict):
    role: Literal['system', 'user', 'assistant']
    content: str = Field(max_length=200000)
    reasoning: str | None = Field(default=None, max_length=200000)
    image: str | None = Field(default=None, max_length=900000)


class Inference(Strict):
    model: str
    action: Literal['generate', 'load'] = 'generate'
    idle_timeout_seconds: int = Field(default=300, ge=60, le=3600)
    conversation_id: str | None = Field(default=None, max_length=64)
    engine: Literal['llama', 'vllm', 'diffusers'] = 'llama'
    workflow: Literal['chat', 't2i', 't2v', 'r2v'] = 'chat'
    media_format: Literal['diffusers', 'comfyui'] = 'diffusers'
    comfy_architecture: Literal['anima', 'sd15', 'sdxl', 'flux', 'wan21'] = 'anima'
    text_encoder: str = ''
    text_encoder_2: str = ''
    vae: str = ''
    clip_vision: str = ''
    device: Literal['auto', 'cpu', 'cuda', 'mps'] = 'auto'
    context_length: int = Field(default=4096, ge=256, le=131072)
    max_tokens: int = Field(default=512, ge=1, le=16384)
    temperature: float = Field(default=0.7, ge=0, le=2)
    top_k: int = Field(default=40, ge=0, le=1000)
    top_p: float = Field(default=0.95, gt=0, le=1)
    gpu_memory_utilization: float = Field(default=0.75, gt=0, le=0.95)
    tensor_parallel_size: int = Field(default=1, ge=1, le=16)
    gpu_layers: int = Field(default=-1, ge=-1, le=1000)
    cpu_offload: bool = True
    cpu_offload_gb: float = Field(default=4, ge=0.25, le=256)
    messages: list[Message] = Field(default_factory=list, max_length=100)
    prompt: str = Field(default='', max_length=10000)
    negative_prompt: str = Field(default='', max_length=10000)
    image: str | None = Field(default=None, max_length=900000)
    material_id: str | None = Field(default=None, max_length=64)
    mmproj: str = ''
    vision_handler: Literal['none', 'llava15', 'llava16', 'moondream'] = 'none'
    width: int = Field(default=512, ge=128, le=2048, multiple_of=8)
    height: int = Field(default=512, ge=128, le=2048, multiple_of=8)
    sampler: Literal['euler', 'default'] = 'euler'
    steps: int = Field(default=25, ge=1, le=200)
    guidance_scale: float = Field(default=7.0, ge=0, le=30)
    frames: int = Field(default=17, ge=2, le=257)
    fps: int = Field(default=8, ge=1, le=60)
    seed: int = Field(default=42, ge=0, le=2147483647)

    @model_validator(mode='after')
    def workflow_contract(self):
        if (self.workflow == 'chat') != (self.engine != 'diffusers'):
            raise ValueError('文本会话使用 llama/vLLM，媒体工作流使用 Diffusers')
        if self.workflow != 'chat' and self.media_format == 'comfyui':
            if not self.text_encoder or not self.vae: raise ValueError('请选择独立的文本编码器与 VAE 权重')
            if (self.workflow != 't2i') != (self.comfy_architecture == 'wan21'): raise ValueError('当前视频分离权重工作流支持 Wan 2.1，图像工作流请选择图像架构')
            if self.comfy_architecture in ('sdxl', 'flux') and not self.text_encoder_2: raise ValueError('此架构需要两个文本编码器')
            if self.comfy_architecture == 'wan21' and (self.frames - 1) % 4: raise ValueError('Wan 2.1 帧数必须为 4n+1')
            if self.workflow == 'r2v' and not self.clip_vision: raise ValueError('Wan 2.1 参考图工作流需要 CLIP Vision 权重')
        if self.action == 'load' and self.workflow != 'chat': raise ValueError('手动加载只适用于 LLM')
        if self.workflow == 'chat' and self.action == 'generate' and (not self.messages or self.messages[-1].role != 'user'):
            raise ValueError('请提供最后一条用户消息')
        if self.workflow == 'chat' and self.max_tokens >= self.context_length:
            raise ValueError('输出长度必须小于上下文长度')
        if self.workflow == 'r2v' and not self.image and not self.material_id:
            raise ValueError('参考图生视频需要上传图片')
        if self.workflow in ('t2i', 't2v') and not self.prompt.strip():
            raise ValueError('请输入提示词')
        return self


class Ablation(Strict):
    model: str
    toml: str = Field(max_length=200000)
    fields: dict = Field(default_factory=dict)


class Recommendation(Strict):
    model: str
    engine: Literal['llama', 'vllm', 'diffusers']


class Conversation(Strict):
    title: str = Field(default='新会话', max_length=120)
    model: str = ''
    engine: Literal['llama', 'vllm'] = 'llama'
    messages: list[Message] = Field(default_factory=list, max_length=100)
