// GPT-J and Phi-2 use a shared pre-LN, parallel attention/GELU MLP, and a biased output head.
// Normalize GPT-J's separate projections and adjacent-pair rotary layout for libllama's Phi-2 graph.
#pragma once
#include "gguf.h"
#include "ggml.h"
#include <fstream>
#include <vector>
#include <string>
#include <memory>
#include <stdexcept>
#include <algorithm>

static void prepare_gptj_layout(bool vocabulary_only) {
    using File = std::unique_ptr<gguf_context, decltype(&gguf_free)>;
    using Context = std::unique_ptr<ggml_context, decltype(&ggml_free)>;
    ggml_context *meta = nullptr;
    File src(gguf_init_from_file("weights.gguf", {true,&meta}), gguf_free);
    Context tensors(meta, ggml_free);
    File dest(gguf_init_empty(), gguf_free);
    if (!src || !meta || !dest) throw std::runtime_error("Invalid GPT-J tensor directory");
    auto u32 = [&](const char *key) {
        auto idx = gguf_find_key(src.get(),key);
        if (idx < 0 || gguf_get_kv_type(src.get(),idx) != GGUF_TYPE_UINT32)
            throw std::runtime_error(std::string("Missing GPT-J parameter: ")+key);
        return gguf_get_val_u32(src.get(),idx);
    };
    auto arch = gguf_find_key(src.get(),"general.architecture");
    if (arch < 0 || gguf_get_kv_type(src.get(),arch) != GGUF_TYPE_STRING ||
        std::string(gguf_get_val_str(src.get(),arch)) != "gptj") throw std::runtime_error("Expected GPT-J");
    auto layers=u32("gptj.block_count"), heads=u32("gptj.attention.head_count");
    auto width=u32("gptj.embedding_length"), rotary=u32("gptj.rope.dimension_count");
    auto context=u32("gptj.context_length");
    if (!layers || layers>256 || !heads || !width || width>65536 || width%heads || !rotary || rotary%2 || rotary>width/heads)
        throw std::runtime_error("Invalid GPT-J head dimensions");
    auto ff=ggml_get_tensor(meta,"blk.0.ffn_up.weight");
    auto eps=gguf_find_key(src.get(),"gptj.attention.layer_norm_epsilon");
    if (!ff || ff->ne[0]!=width || ff->ne[1]<=0 || ff->ne[1]>262144 || eps<0 ||
        gguf_get_kv_type(src.get(),eps)!=GGUF_TYPE_FLOAT32) throw std::runtime_error("Incomplete GPT-J model");
    gguf_set_kv(dest.get(),src.get());
    gguf_set_val_str(dest.get(),"general.architecture","phi2");
    gguf_set_val_u32(dest.get(),"phi2.block_count",layers);
    gguf_set_val_u32(dest.get(),"phi2.attention.head_count",heads);
    gguf_set_val_u32(dest.get(),"phi2.context_length",context);
    gguf_set_val_u32(dest.get(),"phi2.embedding_length",width);
    gguf_set_val_u32(dest.get(),"phi2.rope.dimension_count",rotary);
    gguf_set_val_u32(dest.get(),"phi2.feed_forward_length",(uint32_t)ff->ne[1]);
    gguf_set_val_f32(dest.get(),"phi2.attention.layer_norm_epsilon",gguf_get_val_f32(src.get(),eps));
    const auto freq=gguf_find_key(src.get(),"gptj.rope.freq_base");
    if (freq>=0 && gguf_get_kv_type(src.get(),freq)==GGUF_TYPE_FLOAT32)
        gguf_set_val_f32(dest.get(),"phi2.rope.freq_base",gguf_get_val_f32(src.get(),freq));
    if (vocabulary_only) {
        if (!gguf_write_to_file(dest.get(),"layout.gguf",true)) throw std::runtime_error("Cannot write GPT-J vocabulary");
        return;
    }
    const int64_t count=gguf_get_n_tensors(src.get());
    if (count>32768) throw std::runtime_error("Unexpected GPT-J tensor count");
    Context shapes(ggml_init({(size_t)(layers*7+4)*ggml_tensor_overhead(),nullptr,true}),ggml_free);
    if (!shapes) throw std::runtime_error("Cannot allocate GPT-J tensor directory");
    std::vector<bool> reorder(count,false);
    for (int64_t i=0;i<count;i++) {
        std::string name=gguf_get_tensor_name(src.get(),i);
        auto t=ggml_get_tensor(meta,name.c_str());
        for (char part : {'q','k','v'}) {
            auto old=std::string(".attn.")+part+"_proj.";
            auto pos=name.find(old);
            if (pos!=std::string::npos) name.replace(pos,old.size(),std::string(".attn_")+part+".");
            const auto stem=std::string(".attn_")+part+".";
            if (name.find(stem+"weight")!=std::string::npos || name.find(stem+"bias")!=std::string::npos) {
                const bool is_bias=name.compare(name.size()-5,5,".bias")==0;
                if (t->ne[0]!=width || t->ne[1]!=(is_bias?1:width)) throw std::runtime_error("Invalid GPT-J projection");
                reorder[i]=part!='v';
            }
        }
        ggml_set_name(t,name.c_str());
        gguf_add_tensor(dest.get(),t);
    }
    auto embedding=ggml_get_tensor(meta,"token_embd.weight");
    if (!embedding || embedding->ne[0]!=width || embedding->ne[1]<=0)
        throw std::runtime_error("Invalid GPT-J embedding");
    const bool tied=gguf_find_tensor(dest.get(),"output.weight")<0;
    if (tied) {
        auto t=ggml_dup_tensor(shapes.get(),embedding);
        ggml_set_name(t,"output.weight"); gguf_add_tensor(dest.get(),t);
    }
    auto bias=[&](const std::string &name,int64_t length) {
        if (gguf_find_tensor(dest.get(),name.c_str())>=0) return;
        auto t=ggml_new_tensor_1d(shapes.get(),GGML_TYPE_F32,length);
        ggml_set_name(t,name.c_str()); gguf_add_tensor(dest.get(),t);
    };
    bias("output.bias",embedding->ne[1]);
    bias("output_norm.bias",width);
    for (uint32_t layer=0;layer<layers;++layer) {
        auto prefix="blk."+std::to_string(layer)+".";
        for (auto part : {"attn_norm","attn_q","attn_k","attn_v","attn_output","ffn_down"})
            bias(prefix+part+".bias",width);
        bias(prefix+"ffn_up.bias",ff->ne[1]);
    }
    if (!gguf_write_to_file(dest.get(),"layout.gguf",true)) throw std::runtime_error("Cannot write GPT-J tensor directory");
    std::ifstream in("weights.gguf",std::ios::binary);
    std::fstream out("layout.gguf",std::ios::binary|std::ios::in|std::ios::out);
    in.exceptions(std::ios::failbit|std::ios::badbit);
    out.exceptions(std::ios::failbit|std::ios::badbit);
    std::vector<char> buffer(1024*1024);
    const auto data=gguf_get_meta_size(dest.get());
    const int64_t copied=count+(tied ? 1 : 0);
    for (int64_t i=0;i<copied;i++) {
        int64_t source_index=i<count ? i : gguf_find_tensor(src.get(),"token_embd.weight");
        auto offset=gguf_get_data_offset(src.get())+gguf_get_tensor_offset(src.get(),source_index);
        in.seekg(offset);
        out.seekp(data+gguf_get_tensor_offset(dest.get(),i));
        size_t bytes=gguf_get_tensor_size(src.get(),source_index);
        if (i<count && reorder[i]) {
            // Change only row order, preserving every quantization block and its scale.
            size_t head_bytes=bytes/heads, head_width=width/heads, row_bytes=head_bytes/head_width;
            if (!row_bytes || row_bytes*width!=bytes) throw std::runtime_error("Invalid GPT-J row size");
            std::vector<char> head(head_bytes), permuted(head_bytes);
            for (uint32_t h=0;h<heads;++h) {
                in.read(head.data(),head.size());
                for (size_t j=0;j<head_width;++j) {
                    auto source=j>=rotary ? j : (j%(rotary/2))*2+j/(rotary/2);
                    std::copy_n(head.data()+source*row_bytes,row_bytes,permuted.data()+j*row_bytes);
                }
                out.write(permuted.data(),permuted.size());
            }
        } else while (bytes) {
            size_t n=std::min(bytes,buffer.size());
            in.read(buffer.data(),n); out.write(buffer.data(),n); bytes-=n;
        }
    }
    // Bias tensors absent from the checkpoint represent zeros.
    std::fill(buffer.begin(),buffer.end(),0);
    for (int64_t i=copied;i<gguf_get_n_tensors(dest.get());++i) {
        out.seekp(data+gguf_get_tensor_offset(dest.get(),i));
        size_t remaining=gguf_get_tensor_size(dest.get(),i);
        while (remaining) {
            auto n=std::min(remaining,buffer.size());out.write(buffer.data(),n);remaining-=n;
        }
    }
    out.close();
}
