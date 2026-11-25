#pragma once
#include "gguf.h"
#include <array>
#include <future>
#ifdef _WIN32
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include <wincrypt.h>

// Hold the checked source read-only while GGUF reopens and seeks in it.
// This binds a compact import to the digest displayed at import preview.
struct compact_import_source {
    HANDLE file=INVALID_HANDLE_VALUE;
    HCRYPTPROV provider=0;
    HCRYPTHASH hash=0;
    ~compact_import_source() {
        if (hash) CryptDestroyHash(hash);
        if (provider) CryptReleaseContext(provider,0);
        if (file!=INVALID_HANDLE_VALUE) CloseHandle(file);
    }
    void verify(const std::string &source,const std::string &expected) {
        if (expected.empty()) return;
        file=CreateFileW(std::filesystem::u8path(source).c_str(),GENERIC_READ,FILE_SHARE_READ,nullptr,OPEN_EXISTING,
                         FILE_FLAG_SEQUENTIAL_SCAN,nullptr);
        if (file==INVALID_HANDLE_VALUE) throw std::runtime_error("无法锁定待导入的 GGUF 原文件。");
        if (!CryptAcquireContextW(&provider,nullptr,nullptr,PROV_RSA_AES,CRYPT_VERIFYCONTEXT) ||
            !CryptCreateHash(provider,CALG_SHA_256,0,0,&hash)) throw std::runtime_error("无法初始化 GGUF 校验。");
        std::vector<BYTE> buffer(4*1024*1024);
        for (;;) {
            DWORD count=0;
            if (!ReadFile(file,buffer.data(),static_cast<DWORD>(buffer.size()),&count,nullptr))
                throw std::runtime_error("读取 GGUF 原文件失败。");
            if (!count) break;
            if (!CryptHashData(hash,buffer.data(),count,0)) throw std::runtime_error("无法校验 GGUF 原文件。");
        }
        BYTE digest[32];
        DWORD length=sizeof(digest);
        if (!CryptGetHashParam(hash,HP_HASHVAL,digest,&length,0) || length!=sizeof(digest))
            throw std::runtime_error("无法完成 GGUF 原文件校验。");
        static constexpr char digits[]="0123456789abcdef";
        std::string hex;
        for (auto b:digest) { hex+=digits[b>>4]; hex+=digits[b&15]; }
        if (hex!=expected) throw std::runtime_error("GGUF 原文件与导入预览的摘要不符。");
    }
};
#endif

// Keep audio.cpp's tokenizer, embedded sidecars, original tensor ranks and
// logical names. Only requantize the aligned attention and MLP matrices in
// the language backbone and DramaBox DiT. Convolutions, norms and the vocoder keep their type.
static void compact_weights(const std::string &source, const std::string &dest, bool audio,
                            const std::set<std::string> &matrices,const std::string &expected={},
                            std::istream *payload=nullptr, bool directory_only=false) {
    const auto out_path = std::filesystem::u8path(dest);
    if (std::filesystem::exists(out_path)) throw std::runtime_error("Output already exists");
#ifdef _WIN32
    compact_import_source locked;
    locked.verify(source,expected);
#else
    if (!expected.empty()) throw std::runtime_error("Verified compact import requires Windows.");
#endif
    std::unique_ptr<gguf_context, decltype(&gguf_free)> ctx(
        gguf_init_from_file(source.c_str(), {true, nullptr}), gguf_free);
    if (!ctx) throw std::runtime_error("Cannot read GGUF directory");
    const auto names = gguf_find_key(ctx.get(), "audiocpp.tensor_names");
    const auto count = gguf_get_n_tensors(ctx.get());
    if (audio && (names < 0 || gguf_get_kv_type(ctx.get(), names) != GGUF_TYPE_ARRAY ||
        gguf_get_arr_type(ctx.get(), names) != GGUF_TYPE_STRING ||
        gguf_get_arr_n(ctx.get(), names) != static_cast<size_t>(count)))
        throw std::runtime_error("Missing audio.cpp logical tensor names");
    ggml_type compact_type = GGML_TYPE_Q4_K;
    bool deepseek_mixed=false;
    llama_ftype file_type = LLAMA_FTYPE_MOSTLY_Q4_K_M;
    if (!audio) {
        const auto id = gguf_find_key(ctx.get(), "general.architecture");
        if (id < 0 || gguf_get_kv_type(ctx.get(), id) != GGUF_TYPE_STRING)
            throw std::runtime_error("Missing language architecture");
        const std::string arch = gguf_get_val_str(ctx.get(), id);
        if (arch == "cogvlm" || arch == "rnd1") {compact_type=GGML_TYPE_Q4_0; file_type=LLAMA_FTYPE_MOSTLY_Q4_0;}
        else if (arch == "kimi-k3") {compact_type=GGML_TYPE_Q2_0; file_type=LLAMA_FTYPE_MOSTLY_Q2_0;}
        else if (arch == "mistral4" || arch == "step35" || arch == "dbrx" || arch == "maion-coder") {compact_type=GGML_TYPE_Q1_0; file_type=LLAMA_FTYPE_MOSTLY_Q1_0;}
        else if (arch == "deepseek4") {compact_type=GGML_TYPE_Q1_0; file_type=LLAMA_FTYPE_MOSTLY_Q1_0; deepseek_mixed=true;}
        else throw std::runtime_error("Unsupported compact language layout");
    }
    struct Entry {
        size_t offset, bytes;
        int64_t columns, rows;
        ggml_type source_type, output_type;
        bool convert;
    };
    std::vector<Entry> tensors;
    const auto base = gguf_get_data_offset(ctx.get());
    size_t changed = 0;
    for (int64_t i = 0; i < count; ++i) {
        const std::string name = audio ? gguf_get_arr_str(ctx.get(), names, i) : gguf_get_tensor_name(ctx.get(), i);
        const auto *ne = gguf_get_tensor_ne(ctx.get(), i);
        const bool backbone = name.rfind("model/backbone_llm.", 0) == 0 || name.rfind("gemma/language_model.", 0) == 0;
        const bool linear = name.find(".layers.") != std::string::npos &&
                            (name.find(".self_attn.") != std::string::npos || name.find(".mlp.") != std::string::npos);
        const bool drama_linear = name.rfind("dit/model.diffusion_model.transformer_blocks.", 0) == 0 &&
            (name.find(".audio_attn1.to_") != std::string::npos || name.find(".audio_attn2.to_") != std::string::npos ||
             name.find(".audio_ff.net.") != std::string::npos);
        const auto source_type = gguf_get_tensor_type(ctx.get(), i);
        const auto output_type = deepseek_mixed && name.find("_exps.weight")==std::string::npos ? GGML_TYPE_Q4_0 : compact_type;
        const bool matrix = name.size() >= 7 && name.compare(name.size()-7, 7, ".weight") == 0 &&
                            ne[0] > 0 && ne[0] <= 1024*1024 && ne[1] > 1 && ne[3] == 1;
        const bool convert = matrix && (audio
            ? ((backbone && linear) || drama_linear) && source_type == GGML_TYPE_Q8_0 && ne[0] % 256 == 0 && ne[2] == 1
            : matrices.count(name) && ne[0] % ggml_blck_size(output_type) == 0 &&
              ggml_row_size(source_type,ne[0])>ggml_row_size(output_type,ne[0]));
        tensors.push_back({base + gguf_get_tensor_offset(ctx.get(), i), gguf_get_tensor_size(ctx.get(), i),
                           ne[0], ne[1] * ne[2], source_type, output_type, convert});
        if (convert) ++changed;
    }
    if (!changed || (!audio && changed!=matrices.size())) throw std::runtime_error("Unmatched compact weight matrices");
    for (int64_t i = 0; i < count; ++i) if (tensors[i].convert)
        gguf_set_tensor_type(ctx.get(), gguf_get_tensor_name(ctx.get(), i), tensors[i].output_type);
    if (audio) gguf_set_val_str(ctx.get(), "audiocpp.weight_type", "q4_k");
    else {
        gguf_set_val_u32(ctx.get(), "general.file_type", file_type);
        gguf_set_val_bool(ctx.get(), "ailab.cpu_no_repack", true);
        gguf_set_val_u32(ctx.get(), "general.quantization_version", GGML_QNT_VERSION);
    }
    const size_t header_size = gguf_get_meta_size(ctx.get());
    std::ifstream disk(std::filesystem::u8path(source), std::ios::binary);
    std::istream &input=payload ? *payload : disk;
    std::ofstream output(out_path, std::ios::binary);
    input.exceptions(std::ios::failbit | std::ios::badbit);
    output.exceptions(std::ios::failbit | std::ios::badbit);
    {
        std::vector<char> header(header_size);
        gguf_get_meta_data(ctx.get(), header.data());
        output.write(header.data(), header.size());
    }
    if (directory_only) {
        const size_t alignment=gguf_get_alignment(ctx.get());
        const size_t end=header_size+gguf_get_tensor_offset(ctx.get(),count-1)+gguf_get_tensor_size(ctx.get(),count-1);
        output.close();
        emit({{"type","directory"},{"file_bytes",end+(alignment-end%alignment)%alignment},{"converted_tensors",changed}});
        return;
    }
    struct row_chunk {
        std::vector<char> source, packed;
        std::vector<float> values;
        std::future<void> work;
    };
    std::array<row_chunk,4> chunks;
    const unsigned lanes=audio ? 1u : std::clamp(std::thread::hardware_concurrency()/2,1u,4u);
    std::vector<char> raw(4*1024*1024);
    const size_t alignment = gguf_get_alignment(ctx.get());
    const std::vector<char> zeros(alignment, 0);
    size_t consumed=0;
    for (int64_t i = 0; i < count; ++i) {
        const auto &t = tensors[i];
        if (payload) {
            if (t.offset<consumed) throw std::runtime_error("Streamed GGUF tensors must follow file order");
            input.ignore(static_cast<std::streamsize>(t.offset-consumed));
            if (static_cast<size_t>(input.gcount())!=t.offset-consumed)
                throw std::runtime_error("Incomplete source GGUF padding");
            consumed=t.offset+t.bytes;
        } else input.seekg(t.offset);
        const auto offset = header_size + gguf_get_tensor_offset(ctx.get(), i);
        if (static_cast<size_t>(output.tellp()) != offset) throw std::runtime_error("Invalid GGUF output offset");
        if (t.convert) {
            const int64_t rows_per_chunk = std::max<int64_t>(1, (audio ? 1 : 2)*1024*1024 / t.columns);
            const auto to_float = ggml_get_type_traits(t.source_type)->to_float;
            if (!to_float) throw std::runtime_error("Missing GGML row decoder");
            const size_t in_row = ggml_row_size(t.source_type, t.columns);
            const size_t out_row = ggml_row_size(t.output_type, t.columns);
            const auto policy=lanes>1 && t.rows>rows_per_chunk ? std::launch::async : std::launch::deferred;
            for (int64_t row=0; row<t.rows;) {
                unsigned used=0;
                while (used<lanes && row<t.rows) {
                    auto &chunk=chunks[used++];
                    const auto rows=std::min(rows_per_chunk,t.rows-row);
                    chunk.source.resize(rows*in_row);
                    chunk.values.resize(rows*t.columns);
                    chunk.packed.resize(rows*out_row);
                    input.read(chunk.source.data(),chunk.source.size());
                    chunk.work=std::async(policy,[&chunk,&t,to_float,rows] {
                        to_float(chunk.source.data(),chunk.values.data(),chunk.values.size());
                        const size_t bytes=ggml_quantize_chunk(t.output_type,chunk.values.data(),chunk.packed.data(),
                                                              0,rows,t.columns,nullptr);
                        if (bytes!=chunk.packed.size()) throw std::runtime_error("Incomplete weight quantization");
                    });
                    row+=rows;
                }
                // Quantization is independent per row. Commit in original GGUF order.
                for (unsigned j=0;j<used;++j) {
                    chunks[j].work.get();
                    output.write(chunks[j].packed.data(),chunks[j].packed.size());
                }
            }
        } else {
            raw.resize(4*1024*1024);
            for (size_t left = t.bytes; left;) {
                const size_t n = std::min(left, raw.size());
                input.read(raw.data(), n);
                output.write(raw.data(), n);
                left -= n;
            }
        }
        const size_t size = gguf_get_tensor_size(ctx.get(), i);
        if (static_cast<size_t>(output.tellp()) != offset + size) throw std::runtime_error("Incorrect GGUF tensor size");
        output.write(zeros.data(), (alignment - size % alignment) % alignment);
    }
    if (payload) {
        const auto total=std::filesystem::file_size(std::filesystem::u8path(source));
        if (total<consumed) throw std::runtime_error("Invalid source GGUF length");
        input.ignore(static_cast<std::streamsize>(total-consumed));
        if (static_cast<uint64_t>(input.gcount())!=total-consumed) throw std::runtime_error("Incomplete source GGUF tail");
    }
    output.close();
    emit({{"type","converted"},{"tensor_count",count},{audio ? "q4_k_tensors" : "converted_tensors",changed}});
}
