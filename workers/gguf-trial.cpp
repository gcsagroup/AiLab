// One local request per process. AiLab owns input budgeting, prefill scheduling,
// sampling and output termination. libllama builds the architecture-specific ggml graph.
#if defined(_WIN32) && !defined(_WIN32_WINNT)
#define _WIN32_WINNT 0x0A00
#endif
#include "llama.h"
#include "iris-layout.hpp"
#include "gptj-layout.hpp"
#include "ggml-backend.h"
#include "mtmd-helper.h"
#include <filesystem>
#include <fstream>
#include <nlohmann/json.hpp>
#include <algorithm>
#include <cmath>
#include <chrono>
#include <iostream>
#include <memory>
#include <random>
#include <set>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

using json = nlohmann::json;
using Clock = std::chrono::steady_clock;
static double milliseconds(Clock::time_point start, Clock::time_point end) {
    return std::chrono::duration<double, std::milli>(end - start).count();
}

static void emit(const json &event) { std::cout << event.dump() << '\n' << std::flush; }
#include "audio-compact.hpp"
#include "zaya-layout.hpp"
#include "windows-mapped-service.hpp"
#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#endif

static std::string device_id(ggml_backend_dev_t device) {
    return ggml_backend_dev_type(device) == GGML_BACKEND_DEVICE_TYPE_CPU ? "cpu" : ggml_backend_dev_name(device);
}
static json inventory() {
    json items = json::array();
    for (size_t i = 0; i < ggml_backend_dev_count(); ++i) {
        auto device = ggml_backend_dev_get(i);
        auto type = ggml_backend_dev_type(device);
        if (type != GGML_BACKEND_DEVICE_TYPE_CPU && type != GGML_BACKEND_DEVICE_TYPE_GPU &&
            type != GGML_BACKEND_DEVICE_TYPE_IGPU) continue;
        size_t free_bytes, total;
        ggml_backend_dev_memory(device, &free_bytes, &total);
        items.push_back({{"id",device_id(device)},{"name",ggml_backend_dev_description(device)},
            {"backend",ggml_backend_dev_name(device)},{"memory_bytes",total},{"free_bytes",free_bytes}});
    }
    return items;
}
static void tokenize(std::vector<llama_token> &result, const llama_vocab *vocab,
                     const std::string &text, bool special) {
    int n = llama_tokenize(vocab,text.data(),text.size(),nullptr,0,false,special);
    if (n == 0) return;
    if (n > 0) throw std::runtime_error("token count failed");
    size_t old = result.size();
    result.resize(old-n);
    if (llama_tokenize(vocab,text.data(),text.size(),result.data()+old,-n,false,special) != -n)
        throw std::runtime_error("tokenization failed");
}
static std::string hex(const std::string &bytes) {
    const char *digits = "0123456789abcdef";
    std::string out;
    for (unsigned char b:bytes) { out.push_back(digits[b >> 4]); out.push_back(digits[b & 15]); }
    return out;
}
// Keep the longest possible partial stop in the buffer, including byte-split UTF-8.
static bool flush_visible(std::string &buffer, const std::vector<std::string> &stops, bool final) {
    size_t cut = buffer.size(), keep = 0;
    bool stopped = false;
    for (const auto &s:stops) {
        auto pos = buffer.find(s);
        if (pos != std::string::npos) { cut = std::min(cut,pos); stopped = true; }
        if (!final) for (size_t k=1;k<s.size() && k<=buffer.size();++k)
            if (buffer.compare(buffer.size()-k,k,s,0,k)==0) keep=std::max(keep,k);
    }
    if (!stopped) cut -= keep;
    if (cut) emit({{"type","bytes"},{"hex",hex(buffer.substr(0,cut))}});
    buffer.erase(0,cut);
    return stopped;
}
#include "gguf-special.hpp"
#include "cogvlm-prefill.hpp"

static void run(const json &request) {
    const std::string action = request.at("action");
    if (action == "compact-audio" || action == "compact-language") {
        const bool streamed=request.value("stream_payload",false);
        if (streamed && (action!="compact-language" || request.contains("source_sha256")))
            throw std::runtime_error("A streamed conversion must be verified by its transfer owner before publication");
        compact_weights(request.at("model"),request.at("output"),action == "compact-audio",
                        request.value("matrices",std::set<std::string>{}),request.value("source_sha256",std::string{}),
                        streamed ? &std::cin : nullptr,request.value("directory_only",false));
        return;
    }
    if (action == "prepare-zaya-layout") { prepare_zaya(request.at("model"),request.at("output")); return; }
    if (action == "devices") { emit({{"type","devices"},{"items",inventory()}}); return; }
    const bool check = action == "inspect";
    if (!check && action != "generate") throw std::runtime_error("Unknown action");
    const auto &r = request.at("runtime");
    const std::string selected = r.at("device_id");
    ggml_backend_dev_t chosen = nullptr;
    for (size_t i=0;i<ggml_backend_dev_count();++i) {
        auto d=ggml_backend_dev_get(i);
        if (device_id(d)==selected) { chosen=d; break; }
    }
    if (!chosen) throw std::runtime_error("Selected device unavailable");
    auto mp = llama_model_default_params();
    ggml_backend_dev_t devices[] = { selected=="cpu" ? nullptr : chosen, nullptr };
    mp.devices=devices; mp.n_gpu_layers=selected=="cpu" ? 0 : -1;
    if (selected=="cpu" && (r.contains("language_weight_conversion") || r.value("cpu_no_repack",false))) {
        mp.use_extra_bufts=false;
        mp.load_mode=LLAMA_LOAD_MODE_MMAP;
    }
#ifdef _WIN32
    if (selected=="cpu" && r.contains("cpu_working_set_mib")) {
        apply_mapped_budget(GetCurrentProcess(),r.at("cpu_working_set_floor_mib").get<uint64_t>()<<20,
                            r.at("cpu_working_set_mib").get<uint64_t>()<<20);
        mp.lazy_mode=LLAMA_LAZY_MODE_ON;
    }
#endif
    mp.split_mode=LLAMA_SPLIT_MODE_NONE; const bool has_media = request.contains("media") && request["media"].is_string();
    mp.vocab_only=check && !has_media;
    auto file=request.at("model").get<std::string>();
    const std::string ple=request.value("ple_table",std::string{});
    const char *paths[]={file.c_str(),ple.c_str()};
    if (!ple.empty()) {mp.load_mode=LLAMA_LOAD_MODE_MMAP; mp.lazy_mode=LLAMA_LAZY_MODE_ON;}
    const auto load_started = Clock::now();
    std::unique_ptr<llama_model,decltype(&llama_model_free)> model(
        ple.empty() ? llama_model_load_from_file(file.c_str(),mp) : llama_model_load_from_splits(paths,2,mp),llama_model_free);
    if (!model) throw std::runtime_error("GGUF model load failed");
    if (!check) emit({{"type","timing"},{"model_load_ms",milliseconds(load_started,Clock::now())}});
    char architecture[128]{};
    llama_model_meta_val_str(model.get(),"general.architecture",architecture,sizeof(architecture));
    const std::string arch=architecture;
    const char *tpl=llama_model_chat_template(model.get(),nullptr);
    const std::string tmpl=tpl?tpl:"";
    const bool gemma=arch=="gemma4" && tmpl.find("<|turn>model")!=std::string::npos;
    const bool native_prompt=!(gemma || ((arch=="qwen2" || arch=="qwen3" || arch=="qwen3moe" || arch=="qwen35" || arch=="qwen4exp")
                                        && tmpl.find("<|im_start|>")!=std::string::npos));
    const bool seq2seq=arch=="t5", vocoder=arch=="wavtokenizer-dec";
    const bool diffusion=llama_model_is_diffusion(model.get());
    const bool switchable=!native_prompt && tmpl.find("enable_thinking")!=std::string::npos && arch!="qwen2";
    std::string thinking=r.value("thinking","default");
    if (thinking!="default" && !switchable) throw std::runtime_error("Model template has no thinking switch");
    const llama_vocab *vocab=llama_model_get_vocab(model.get());
    std::vector<llama_token> tokens;
    std::string prefix = "<|im_start|>user\n", suffix = "<|im_end|>\n<|im_start|>assistant\n";
    if (arch=="qwen2") prefix = "<|im_start|>system\nYou are Qwen, created by Alibaba Cloud. You are a helpful assistant.<|im_end|>\n" + prefix;
    if (gemma) {
        prefix = (thinking=="enabled" ? "<|turn>system\n<|think|>\n<turn|>\n" : std::string()) + "<|turn>user\n";
        suffix = "<turn|>\n<|turn>model\n";
    } else if (thinking=="disabled") suffix += "<think>\n\n</think>\n\n";
    else if (arch=="qwen35" || (arch=="qwen4exp" && tmpl.find("<think>")!=std::string::npos)) suffix += "<think>\n";
    const std::string prompt = request.at("prompt");
    if (native_prompt) {
        prefix.clear(); suffix.clear();
        if (!tmpl.empty() && !seq2seq && !vocoder) {
            // Render a placeholder so control tokens are parsed only in template text.
            const std::string marker="AiLabPromptMarker";
            const llama_chat_message message{"user",marker.c_str()};
            int size=llama_chat_apply_template(tpl,&message,1,true,nullptr,0);
            if (size<=0) throw std::runtime_error("当前后端不支持该模型的对话模板。");
            std::string formatted(size+1,'\0');
            int n=llama_chat_apply_template(tpl,&message,1,true,formatted.data(),formatted.size());
            if(n!=size)throw std::runtime_error("无法格式化模型输入。");
            formatted.resize(n);
            auto at=formatted.find(marker);
            if(at==std::string::npos || formatted.find(marker,at+marker.size())!=std::string::npos)
                throw std::runtime_error("该模板不支持单轮对话输入。");
            prefix=formatted.substr(0,at); suffix=formatted.substr(at+marker.size());
        }
    }
    std::unique_ptr<mtmd_context,decltype(&mtmd_free)> mm(nullptr,mtmd_free);
    std::unique_ptr<mtmd_input_chunks,decltype(&mtmd_input_chunks_free)> inputs(nullptr,mtmd_input_chunks_free);
    const bool cog_media=has_media && arch=="cogvlm" && request.value("cogvlm_chat_v1",false);
    const mtmd_input_chunk *cog_image=nullptr;
    std::vector<llama_token> cog_question;
    size_t input_count;
    if (has_media) {
        const auto projection = request.at("projector").get<std::string>();
        auto params = mtmd_context_params_default();
        params.use_gpu=false; params.warmup=false; params.n_threads=6;
        mm.reset(mtmd_init_from_file(projection.c_str(),model.get(),params));
        if (!mm) throw std::runtime_error("Cannot load the GGUF projector for this model");
        std::ifstream file(std::filesystem::u8path(request.at("media").get<std::string>()),std::ios::binary | std::ios::ate);
        const auto size=file.tellg();
        if (!file || size<=0 || size>32*1024*1024) throw std::runtime_error("Invalid media file");
        std::vector<unsigned char> bytes(static_cast<size_t>(size)); file.seekg(0);
        if (!file.read(reinterpret_cast<char*>(bytes.data()),bytes.size())) throw std::runtime_error("Incomplete media file");
        auto loaded=mtmd_helper_bitmap_init_from_buf(mm.get(),bytes.data(),bytes.size(),false,mtmd_helper_init_opt_default());
        std::unique_ptr<mtmd_bitmap,decltype(&mtmd_bitmap_free)> bitmap(loaded.bitmap,mtmd_bitmap_free);
        std::unique_ptr<mtmd_helper_video,decltype(&mtmd_helper_video_free)> video(loaded.video_ctx,mtmd_helper_video_free);
        if (!bitmap || video) throw std::runtime_error("Unsupported image or audio material");
        mtmd_input_text a{prefix.data(),prefix.size(),false,true}, b{prompt.data(),prompt.size(),false,false},
                        c{suffix.data(),suffix.size(),false,true};
        mtmd_input_part p1{&a,nullptr},p2{nullptr,bitmap.get()},p3{&b,nullptr},p4{&c,nullptr};
        const mtmd_input_part* parts[]={&p1,&p2,&p3,&p4};
        inputs.reset(mtmd_input_chunks_init());
        if (!inputs || mtmd_tokenize_from_parts(mm.get(),inputs.get(),parts,4,gemma)!=0) throw std::runtime_error("Media/projector mismatch");
        input_count=mtmd_helper_get_n_tokens(inputs.get());
        if (cog_media) {
            for(size_t i=0;i<mtmd_input_chunks_size(inputs.get());++i) {
                auto *part=mtmd_input_chunks_get(inputs.get(),i);
                if(mtmd_input_chunk_get_type(part)==MTMD_INPUT_CHUNK_TYPE_IMAGE) {
                    if(cog_image) throw std::runtime_error("CogVLM 单次只接收一张图像。");
                    cog_image=part;
                }
            }
            if(!cog_image) throw std::runtime_error("CogVLM 缺少图像。");
            tokenize(cog_question,vocab,"Question: "+prompt+" Answer:",false);
            input_count=1+mtmd_input_chunk_get_n_tokens(cog_image)+cog_question.size();
        }
    } else if (vocoder) {
        const auto ids=json::parse(prompt,nullptr,false);
        if(!ids.is_array() || ids.empty() || ids.size()>4096) throw std::runtime_error("请输入音频码的 JSON 整数数组。");
        char codebook[32]{};
        llama_model_meta_val_str(model.get(),"wavtokenizer-dec.vocab_size",codebook,sizeof(codebook));
        const int64_t size=std::strtoll(codebook,nullptr,10);
        for(const auto &id:ids) {
            if(!id.is_number_integer() || id.get<int64_t>()<0 || id.get<int64_t>()>=size)
                throw std::runtime_error("音频码超出此模型的码本。");
            tokens.push_back(id.get<llama_token>());
        }
        input_count=tokens.size();
    } else {
        if (gemma) tokens.push_back(llama_vocab_bos(vocab));
        tokenize(tokens,vocab,prefix,true); tokenize(tokens,vocab,prompt,false); tokenize(tokens,vocab,suffix,true);
        if(native_prompt && llama_vocab_get_add_bos(vocab) && (tokens.empty() || tokens.front()!=llama_vocab_bos(vocab)))
            tokens.insert(tokens.begin(),llama_vocab_bos(vocab));
        if (seq2seq && llama_vocab_eos(vocab)!=LLAMA_TOKEN_NULL && (tokens.empty() || tokens.back()!=llama_vocab_eos(vocab)))
            tokens.push_back(llama_vocab_eos(vocab));
        input_count=tokens.size();
    }
    unsigned budget=r.at("context_limit");
    const unsigned limit=r.at("max_tokens"), block=r.at("prefill_step_size");
    const unsigned terminal_slots=arch=="rnd1" && llama_vocab_eos(vocab)!=LLAMA_TOKEN_NULL ? 1 : 0;
    // A vocabulary-only model omits allocated hparams; read the original GGUF
    // metadata for preflight just as the full forward context does at execution.
    char model_context[32]{};
    llama_model_meta_val_str(model.get(),(arch+".context_length").c_str(),model_context,sizeof(model_context));
    const auto trained=std::strtoul(model_context,nullptr,10);
    if(native_prompt && trained) budget=std::min(budget,static_cast<unsigned>(trained));
    if (!input_count) throw std::runtime_error("模型词表无法将当前输入编码为词元。请检查权重自带的分词器与输入文本。");
    if (budget<1 || budget>4096 || !limit || !block || block>4096 ||
        (trained && budget>trained) || (vocoder || seq2seq ? input_count>budget || (!vocoder && limit>budget) : input_count+limit+terminal_slots>budget))
        throw std::runtime_error("上下文预算不足或超过模型上限，已完整保留输入。");
    emit({{"type","config"},{"architecture",arch},{"prompt_tokens",input_count},{"device_id",selected},
          {"supports_thinking",switchable},{"context_limit",budget},{"prefill_step_size",block}});
    if (check) return;
    auto cp=llama_context_default_params();
    cogvlm_attention cog;
    if(cog_media) {
        cog.width=llama_model_n_embd(model.get());
        cp.cb_eval=cogvlm_attention::observe;
        cp.cb_eval_user_data=&cog;
    }
    cp.n_ctx=budget; cp.n_batch=std::min(block,budget); cp.n_ubatch=cp.n_batch;
    if (seq2seq || diffusion || vocoder) cp.n_batch=cp.n_ubatch=budget;
    if (vocoder) {cp.embeddings=true;cp.pooling_type=LLAMA_POOLING_TYPE_NONE;}
    cp.n_threads=cp.n_threads_batch=std::max(1u,std::min(8u,std::thread::hardware_concurrency()/2));
    const std::string precision=r.at("kv_precision");
    cp.type_k=cp.type_v=precision=="q8" ? GGML_TYPE_Q8_0 : precision=="q4" ? GGML_TYPE_Q4_0 : GGML_TYPE_F16;
    cp.flash_attn_type=precision=="q4" || precision=="q8" ? LLAMA_FLASH_ATTN_TYPE_ENABLED : LLAMA_FLASH_ATTN_TYPE_AUTO;
    cp.offload_kqv=selected!="cpu"; cp.op_offload=selected!="cpu";
    std::unique_ptr<llama_context,decltype(&llama_free)> ctx(llama_init_from_model(model.get(),cp),llama_free);
    if (!ctx) throw std::runtime_error("所选设备或 KV 精度无法建立推理上下文。");
    if (diffusion) {denoise(ctx.get(),vocab,std::move(tokens),r,limit,arch);return;}
    if (vocoder) {decode_codes(ctx.get(),model.get(),tokens,request.at("wav"));return;}
    const auto prefill_started = Clock::now();
    if (seq2seq) {
        if(llama_encode(ctx.get(),llama_batch_get_one(tokens.data(),tokens.size()))!=0)
            throw std::runtime_error("T5 编码器前向计算失败。");
        auto start=llama_model_decoder_start_token(model.get());
        if(start==LLAMA_TOKEN_NULL) start=llama_vocab_bos(vocab);
        if(start==LLAMA_TOKEN_NULL) throw std::runtime_error("T5 缺少解码起始词元。");
        tokens.assign(1,start);
    }
    int chunks=0;
    llama_pos next_pos=0;
    if (cog_media) {
        chunks=cogvlm_image_prefill(cog,ctx.get(),mm.get(),cog_image,llama_vocab_bos(vocab),cog_question,cp.n_batch,next_pos);
    } else if (has_media) {
        if (mtmd_helper_eval_chunks(mm.get(),ctx.get(),inputs.get(),0,0,cp.n_batch,true,&next_pos)!=0)
            throw std::runtime_error("Multimodal prefill failed");
        chunks=static_cast<int>(mtmd_input_chunks_size(inputs.get()));
    }
    for (size_t pos=0; pos<tokens.size();pos+=cp.n_batch) {
        auto count=std::min<size_t>(cp.n_batch,tokens.size()-pos);
        if (llama_decode(ctx.get(),llama_batch_get_one(tokens.data()+pos,count))!=0) throw std::runtime_error("GGUF prefill failed");
        ++chunks;
    }
    llama_synchronize(ctx.get());
    emit({{"type","prefill"},{"chunks",chunks},{"ubatch",llama_n_ubatch(ctx.get())},{"kv_precision",precision=="auto"?"f16":precision},
          {"prefill_ms",milliseconds(prefill_started,Clock::now())},{"prefill_tokens",input_count}});
    auto chain=std::unique_ptr<llama_sampler,decltype(&llama_sampler_free)>(llama_sampler_chain_init(llama_sampler_chain_default_params()),llama_sampler_free);
    const float temperature=r.at("temperature"), top_p=r.at("top_p");
    if (temperature==0) llama_sampler_chain_add(chain.get(),llama_sampler_init_greedy());
    else {
        llama_sampler_chain_add(chain.get(),llama_sampler_init_temp(temperature));
        llama_sampler_chain_add(chain.get(),llama_sampler_init_top_p(top_p,1));
        // libllama reserves UINT32_MAX to mean random. AiLab accepts it as an ordinary reproducible seed.
    }
    std::mt19937 rng(r.at("seed").get<uint32_t>());
    std::vector<llama_token_data> candidates;
    if (temperature>0) candidates.resize(llama_vocab_n_tokens(vocab));
    std::vector<std::string> stops=r.at("stop");
    std::string pending,reason="length";
    unsigned generated=0;
    Clock::time_point decode_started;
    double decode_ms=0;
    unsigned decode_tokens=0;
    auto last_report=Clock::now();
    while (generated<limit) {
        llama_token next;
        if (temperature==0) next=llama_sampler_sample(chain.get(),ctx.get(),-1);
        else {
            const float *logits=llama_get_logits_ith(ctx.get(),-1);
            for (size_t i=0;i<candidates.size();++i) candidates[i]={static_cast<llama_token>(i),logits[i],0};
            llama_token_data_array arr{candidates.data(),candidates.size(),-1,false};
            llama_sampler_apply(chain.get(),&arr);
            float highest=arr.data[0].logit;
            for(size_t i=1;i<arr.size;++i) highest=std::max(highest,arr.data[i].logit);
            std::vector<double> weights(arr.size);
            for(size_t i=0;i<arr.size;++i) weights[i]=std::exp(double(arr.data[i].logit)-highest);
            next=arr.data[std::discrete_distribution<size_t>(weights.begin(),weights.end())(rng)].id;
        }
        // Sampling consumes the previous one-token forward pass, including the pass that selects EOS.
        if (generated) {
            const auto sampled=Clock::now();
            decode_ms+=milliseconds(decode_started,sampled);
            ++decode_tokens;
            if (milliseconds(last_report,sampled)>=500) {
                emit({{"type","timing"},{"decode_ms",decode_ms},{"decode_tokens",decode_tokens},{"completion_tokens",generated}});
                last_report=sampled;
            }
        }
        if (llama_vocab_is_eog(vocab,next)) { reason="eos"; break; }
        ++generated;
        if (generated==1) emit({{"type","first_token"}});
        std::vector<char> piece(64);
        int n=llama_token_to_piece(vocab,next,piece.data(),piece.size(),0,true);
        if(n<0){piece.resize(-n); n=llama_token_to_piece(vocab,next,piece.data(),piece.size(),0,true);}
        if(n<0) throw std::runtime_error("GGUF token decode failed");
        pending.append(piece.data(),n);
        if(flush_visible(pending,stops,false)){reason="stop";break;}
        if(generated<limit) {
            decode_started=Clock::now();
            auto batch=llama_batch_get_one(&next,1);
            llama_pos positions[]={next_pos,next_pos,next_pos,0};
            if(cog_media) cog.decode(ctx.get(),batch,next_pos++);
            else {
                if(has_media) { batch.pos=positions; ++next_pos; }
                if(llama_decode(ctx.get(),batch)!=0) throw std::runtime_error("GGUF decode failed");
            }
        }
    }
    if(reason!="stop") flush_visible(pending,stops,true);
    json result={{"type","done"},{"finish_reason",reason},{"completion_tokens",generated}};
    if (decode_tokens) {
        result["decode_tokens"]=decode_tokens;
        result["decode_ms"]=decode_ms;
    }
    emit(result);
}
int main(int argc, char **argv) {
    try {
#ifdef _WIN32
        if (argc >= 4 && std::string(argv[1]) == "--bounded-service")
            return bounded_service(argv[2], argv[3]);
        _setmode(_fileno(stdin), _O_BINARY);
#endif
        std::string line; std::getline(std::cin,line);
        const auto request=json::parse(line);
        if (request.value("action",std::string()) == "prepare-gptj-layout") {
            prepare_gptj_layout(request.value("vocabulary_only",false));
            return 0;
        }
        if (request.value("action", std::string()) == "prepare-iris-layout") {
            prepare_iris_layout(request.at("matrices"));
            return 0;
        }
        if (request.value("cpu_only",false) || (request.contains("runtime") && request.at("runtime").value("device_id","")=="cpu")) {
            const bool avx2=__builtin_cpu_supports("avx2") && __builtin_cpu_supports("fma") && __builtin_cpu_supports("f16c") && __builtin_cpu_supports("bmi2");
            if (!ggml_backend_load(avx2 ? "./ggml-cpu-haswell.dll" : "./ggml-cpu-x64.dll")) throw std::runtime_error("CPU backend unavailable");
        } else ggml_backend_load_all_from_path(".");
        llama_backend_init();
        run(request); llama_backend_free(); return 0;
    } catch (const std::exception &e) { emit({{"type","error"},{"message",e.what()}}); return 1; }
}
