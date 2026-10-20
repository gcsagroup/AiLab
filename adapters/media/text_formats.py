"""Qwen2.5-0.5B 的固定 128 词元导出图；逐层计算与原生实现作独立对照。"""

import torch


class FixedQwen(torch.nn.Module):
    """固定形状避免导出器把动态 Python 维度转换成不兼容的标量算子。"""
    def __init__(self, model):
        super().__init__()
        self.model = model
        self.register_buffer("causal", torch.triu(torch.full((128, 128), -10000.0), diagonal=1)[None, None, :, :])
        cos, sin = model.model.rotary_emb(torch.zeros(1, 128, 896), torch.arange(128)[None, :])
        self.register_buffer("cos", cos[:, None, :, :])
        self.register_buffer("sin", sin[:, None, :, :])

    def forward(self, input_ids, attention_mask):
        mask = self.causal + (1 - attention_mask[:, None, None, :].float()) * -10000.0
        hidden = self.model.model.embed_tokens(input_ids.long())
        for layer in self.model.model.layers:
            x = layer.input_layernorm(hidden)
            attention = layer.self_attn
            q = attention.q_proj(x).view(1, 128, 14, 64).transpose(1, 2)
            k = attention.k_proj(x).view(1, 128, 2, 64).transpose(1, 2)
            v = attention.v_proj(x).view(1, 128, 2, 64).transpose(1, 2)
            q = q * self.cos + torch.cat((-q[..., 32:], q[..., :32]), dim=-1) * self.sin
            k = k * self.cos + torch.cat((-k[..., 32:], k[..., :32]), dim=-1) * self.sin
            k, v = k.repeat_interleave(7, dim=1), v.repeat_interleave(7, dim=1)
            scores = torch.matmul(q, k.transpose(2, 3)) * 0.125 + mask
            y = torch.matmul(torch.softmax(scores, dim=-1), v).transpose(1, 2).reshape(1, 128, 896)
            hidden = hidden + attention.o_proj(y)
            hidden = hidden + layer.mlp(layer.post_attention_layernorm(hidden))
        return self.model.lm_head(self.model.model.norm(hidden)[:, -1, :])
