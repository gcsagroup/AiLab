"""Real Transformers/PEFT SFT, local files only; assistant spans are explicit."""
import json
import hashlib
import math
import re
from pathlib import Path
from common import device, emit, finish


def verify_dataset_reference(config):
    reference = config.get('dataset_reference')
    if not reference: return
    path = Path(config['dataset'])
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        while chunk := stream.read(1024 * 1024): digest.update(chunk)
    if path.stat().st_size != reference['bytes'] or digest.hexdigest() != reference['sha256']:
        raise ValueError('排队后数据文件发生变化，请重新登记并提交训练')


def dataset_files(path):
    """Preserve recognizable held-out splits in downloaded dataset directories."""
    if path.is_file():
        return [path], []
    training, validation = [], []
    metadata = {'dataset_info.json', 'dataset_infos.json', 'dataset_dict.json', 'state.json', 'config.json', 'metadata.json'}
    for file in sorted(path.rglob('*')):
        if not file.is_file() or file.suffix.lower() not in ('.json', '.jsonl', '.parquet') or file.name in metadata:
            continue
        parts = set(re.split(r'[\\/_.-]+', str(file.relative_to(path)).lower()))
        if parts & {'test', 'testing'}:
            emit('status', text='保留测试集，不用于训练：' + str(file.relative_to(path)))
            continue
        (validation if parts & {'validation', 'valid', 'val', 'eval', 'dev'} else training).append(file)
    return training, validation


def dataset_from_path(raw, cache_dir=None):
    from datasets import Dataset, DatasetDict, load_from_disk, concatenate_datasets
    import pyarrow as pa
    import pyarrow.json as paj
    import pyarrow.parquet as pq
    path = Path(raw)
    if path.is_dir() and ((path / 'dataset_dict.json').exists() or (path / 'state.json').exists()):
        data = load_from_disk(str(path))
        if isinstance(data, DatasetDict):
            if 'train' not in data: raise ValueError('数据集字典缺少 train 子集')
            return data['train'], data.get('validation')
        return data, None
    training, validation = dataset_files(path)
    if not training: raise ValueError('数据目录没有训练用 JSON、JSONL 或 Parquet 文件')
    cache = Path(cache_dir or 'data-cache'); cache.mkdir(parents=True, exist_ok=True)
    sequence = 0
    def read(files):
        nonlocal sequence
        parts = []
        for file in files:
            if file.suffix.lower() == '.json':
                with file.open('r', encoding='utf-8-sig') as stream:
                    first = next((c for c in iter(lambda: stream.read(1), '') if not c.isspace()), '')
                if first == '[':
                    rows = json.loads(file.read_text(encoding='utf-8-sig'))
                    if not all(isinstance(row, dict) for row in rows): raise ValueError('JSON 数据应为对象数组')
                    parts.append(Dataset.from_list(rows)); continue
            # Stream local files into short per-job Arrow paths. The HF generic
            # builder duplicates absolute paths and long hashes in Windows locks.
            batches = pq.ParquetFile(file).iter_batches(batch_size=10000) if file.suffix.lower() == '.parquet' else paj.open_json(str(file))
            arrow = cache / f'{sequence}.arrow'; sequence += 1
            writer = None
            try:
                with arrow.open('wb') as output:
                    for batch in batches:
                        if writer is None: writer = pa.ipc.new_stream(output, batch.schema)
                        writer.write_batch(batch)
                    if writer is not None: writer.close()
            finally:
                if hasattr(batches, 'close'): batches.close()
            if writer is None: raise ValueError('数据文件为空：' + file.name)
            parts.append(Dataset.from_file(str(arrow)))
        return concatenate_datasets(parts)
    return read(training), read(validation) if validation else None


def encode_row(row, tokenizer, config):
    maximum = config['max_length']
    if 'messages' in row:
        messages = row['messages']
        if not isinstance(messages, list) or not messages: raise ValueError('messages 必须是非空消息数组')
        if any(not isinstance(m, dict) or m.get('role') not in ('system', 'user', 'assistant') or not isinstance(m.get('content'), str) for m in messages):
            raise ValueError('SFT 仅接受 system/user/assistant 文本消息')
    elif isinstance(row.get('instruction'), str) and isinstance(row.get('output'), str):
        extra = row.get('input', '')
        if not isinstance(extra, str): raise ValueError('input 必须为文本')
        messages = [{'role': 'user', 'content': row['instruction'] + ('\n' + extra if extra else '')}, {'role': 'assistant', 'content': row['output']}]
    elif isinstance(row.get('prompt'), str) and isinstance(row.get('completion'), str):
        messages = [{'role': 'user', 'content': row['prompt']}, {'role': 'assistant', 'content': row['completion']}]
    elif isinstance(row.get(config['text_column']), str):
        if config['loss_scope'] != 'all': raise ValueError('纯文本数据请将损失范围设置为全文；assistant 模式需要 messages 或指令/回答列')
        ids = tokenizer(row[config['text_column']], add_special_tokens=True)['input_ids']
        if tokenizer.eos_token_id is not None: ids.append(tokenizer.eos_token_id)
        if len(ids) > maximum: raise ValueError('样本超过最大序列长度，请清洗数据或提高长度；不会静默截断')
        if len(ids) < 2: raise ValueError('文本样本没有可监督的 token')
        return {'input_ids': ids, 'attention_mask': [1] * len(ids), 'labels': list(ids)}
    else: raise ValueError('支持 messages、instruction/output、prompt/completion 或所选 text 列')
    if not tokenizer.chat_template: raise ValueError('对话数据要求分词器提供 chat_template')
    ids = tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=False, return_dict=False)
    if len(ids) > maximum: raise ValueError('对话超过最大序列长度，请清洗数据或提高长度')
    labels = list(ids) if config['loss_scope'] == 'all' else [-100] * len(ids)
    if config['loss_scope'] == 'assistant':
        for index, message in enumerate(messages):
            if message['role'] != 'assistant': continue
            if index == 0: raise ValueError('对话不能以 assistant 开始')
            prefix = tokenizer.apply_chat_template(messages[:index], tokenize=True, add_generation_prompt=True, return_dict=False)
            upto = tokenizer.apply_chat_template(messages[:index + 1], tokenize=True, add_generation_prompt=False, return_dict=False)
            if ids[:len(prefix)] != prefix or ids[:len(upto)] != upto:
                raise ValueError('此聊天模板的前缀不稳定，无法安全生成 assistant 损失掩码；请改用全文损失或适配模板')
            labels[len(prefix):len(upto)] = ids[len(prefix):len(upto)]
    if not any(value != -100 for value in labels[1:]): raise ValueError('样本没有可监督的回答 token')
    return {'input_ids': ids, 'attention_mask': [1] * len(ids), 'labels': labels}


def run(config):
    verify_dataset_reference(config)
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, Trainer, TrainerCallback, TrainingArguments, DataCollatorForSeq2Seq, set_seed
    from peft import LoraConfig, get_peft_model
    selected = device(config['device']); set_seed(config['seed'])
    precision = config['precision']
    if precision == 'auto':
        precision = 'bfloat16' if (selected == 'cuda' and torch.cuda.is_bf16_supported()) or (selected == 'cpu' and config.get('weight_loading') == 'dequantize') else 'float32'
    if precision == 'bfloat16' and selected == 'cuda' and not torch.cuda.is_bf16_supported(): raise ValueError('设备不支持 BF16')
    if selected == 'mps' and precision != 'float32': raise ValueError('MPS 训练当前使用 FP32，请选择 auto 或 float32')
    if selected == 'cpu' and precision == 'float16': raise ValueError('CPU 训练请选择 FP32 或 BF16')
    dtype = getattr(torch, precision)
    trusted = config.get('trust_remote_code', False)
    from model_compat import install
    compatibility = install(config['model'], trusted)
    tokenizer = AutoTokenizer.from_pretrained(config['model'], local_files_only=True, trust_remote_code=trusted)
    if tokenizer.pad_token_id is None:
        if tokenizer.eos_token_id is None: raise ValueError('分词器需要 pad 或 eos token')
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = 'right'
    # Workers run in their own job directory; original market files stay intact.
    train, validation = dataset_from_path(config['dataset'], cache_dir='data-cache')
    if not len(train): raise ValueError('训练集为空')
    if validation is not None and not len(validation): raise ValueError('验证集为空')
    if validation is None and config['validation_fraction']:
        if len(train) < 2: raise ValueError('至少两条样本才能划分验证集')
        split = train.train_test_split(test_size=config['validation_fraction'], seed=config['seed'])
        train, validation = split['train'], split['test']
    def prepare(data):
        def encode(row, index):
            try: return encode_row(row, tokenizer, config)
            except ValueError as exc: raise ValueError(f'样本 {index + 1}: {exc}') from exc
        return data.map(encode, with_indices=True, remove_columns=data.column_names, load_from_cache_file=False)
    emit('status', text='检查数据并生成监督标签')
    train = prepare(train); validation = prepare(validation) if validation is not None else None
    loading = config.get('weight_loading', 'original')
    extra = dict(compatibility)
    if loading == 'dequantize':
        from transformers import CompressedTensorsConfig
        extra['quantization_config'] = CompressedTensorsConfig(dequantize=True)
        emit('status', text='量化基座：加载时解量化到 ' + precision + ' 后进行 LoRA 微调；内存需求按解量化权重计算，原始量化文件不会修改。')
    elif loading == 'quantized_lora':
        if selected != 'cuda': raise ValueError('bitsandbytes 量化 LoRA 当前需要 CUDA 训练环境')
        extra['device_map'] = {'': 0}
    model = AutoModelForCausalLM.from_pretrained(config['model'], local_files_only=True, trust_remote_code=trusted, use_safetensors=True, dtype=dtype, **extra)
    if loading == 'quantized_lora':
        from peft import prepare_model_for_kbit_training
        model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=config['gradient_checkpointing'])
    if config['method'] == 'lora':
        targets = config['target_modules'] if config['target_modules'] == 'all-linear' else [x.strip() for x in config['target_modules'].split(',') if x.strip()]
        model = get_peft_model(model, LoraConfig(task_type='CAUSAL_LM', r=config['lora_rank'], lora_alpha=config['lora_alpha'], lora_dropout=config['lora_dropout'], target_modules=targets))
    model.config.use_cache = False
    if loading != 'quantized_lora': model.to(selected)
    output = Path(config['output_dir'])
    args = TrainingArguments(output_dir=str(output / 'checkpoints'), num_train_epochs=config['epochs'], max_steps=config['max_steps'],
        per_device_train_batch_size=config['batch_size'], per_device_eval_batch_size=1,
        gradient_accumulation_steps=config['gradient_accumulation'], learning_rate=config['learning_rate'],
        logging_steps=config['logging_steps'], logging_strategy='steps', logging_nan_inf_filter=False, save_steps=config['save_steps'], save_total_limit=2,
        eval_strategy='steps' if validation is not None else 'no', eval_steps=config['save_steps'],
        bf16=precision == 'bfloat16', fp16=precision == 'float16', use_cpu=selected == 'cpu',
        gradient_checkpointing=config['gradient_checkpointing'], gradient_checkpointing_kwargs={'use_reentrant': False},
        report_to=[], disable_tqdm=True, seed=config['seed'], dataloader_pin_memory=selected == 'cuda')
    class Metrics(TrainerCallback):
        def on_log(self, args, state, control, logs=None, **kwargs):
            for name in ('loss', 'eval_loss', 'train_loss'):
                if name in (logs or {}) and not math.isfinite(logs[name]):
                    raise ValueError('训练损失出现 NaN/Inf，请检查精度、学习率和数据')
            clean = {k: float(v) for k, v in (logs or {}).items() if isinstance(v, (float, int)) and math.isfinite(v)}
            emit('metric', step=state.global_step, total=state.max_steps, **clean)
    trainer = Trainer(model=model, args=args, train_dataset=train, eval_dataset=validation,
        data_collator=DataCollatorForSeq2Seq(tokenizer, padding=True, label_pad_token_id=-100), callbacks=[Metrics()])
    trained = trainer.train()
    evaluation = trainer.evaluate() if validation is not None else {}
    saved = output / ('adapter' if config['method'] == 'lora' else 'model')
    trainer.save_model(str(saved)); tokenizer.save_pretrained(str(saved)); trainer.save_state()
    metrics = {k: v for k, v in {**trained.metrics, **evaluation}.items() if isinstance(v, (float, int)) and math.isfinite(v)}
    result = {'model_dir': str(saved), 'kind': 'lora_adapter' if config['method'] == 'lora' else 'full_model',
              'weight_loading': loading, 'base_quantization': config.get('base_quantization'),
              'base_model': config['model'], 'train_samples': len(train), 'validation_samples': len(validation) if validation is not None else 0,
              'device': selected, 'precision': precision, 'metrics': metrics, 'history': trainer.state.log_history}
    finish(config, result)
