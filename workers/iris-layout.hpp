// Convert flattened Comfy GGUF matrices into native F16 rows. Other tensor
// payloads retain their storage type and bytes. Called inside a trial directory.
#pragma once
#include "gguf.h"
#include "ggml.h"
#include <algorithm>
#include <cstring>
#include <fstream>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>
#include <nlohmann/json.hpp>

static void prepare_iris_layout(const nlohmann::json & matrices) {
    if (!matrices.is_object() || matrices.empty() || matrices.size() > 128)
        throw std::runtime_error("Invalid Iris matrix manifest");
    using File = std::unique_ptr<gguf_context, decltype(&gguf_free)>;
    using Context = std::unique_ptr<ggml_context, decltype(&ggml_free)>;
    ggml_context * metadata = nullptr;
    File src(gguf_init_from_file("weights.gguf", {true, &metadata}), gguf_free);
    Context tensors(metadata, ggml_free);
    File dst(gguf_init_empty(), gguf_free);
    Context shapes(ggml_init({(matrices.size()+1)*ggml_tensor_overhead(), nullptr, true}), ggml_free);
    if (!src || !tensors || !dst || !shapes) throw std::runtime_error("Cannot read Iris tensor directory");
    gguf_set_kv(dst.get(), src.get());
    size_t matched = 0;
    const int64_t count = gguf_get_n_tensors(src.get());
    for (int64_t i = 0; i < count; ++i) {
        const char *name = gguf_get_tensor_name(src.get(), i);
        ggml_tensor *t = ggml_get_tensor(tensors.get(), name);
        if (!t) throw std::runtime_error("Missing Iris tensor");
        if (matrices.contains(name)) {
            const auto dims = matrices.at(name).get<std::vector<int64_t>>();
            if (dims.size() != 2 || dims[0] != 6826 || dims[1] != 2560 || ggml_nelements(t) != dims[0]*dims[1])
                throw std::runtime_error("Invalid packed Iris matrix size");
            t = ggml_new_tensor_2d(shapes.get(), GGML_TYPE_F16, dims[0], dims[1]);
            ggml_set_name(t, name);
            ++matched;
        }
        gguf_add_tensor(dst.get(), t);
    }
    if (matched != matrices.size() || !gguf_write_to_file(dst.get(), "iris-layout.gguf", true))
        throw std::runtime_error("Cannot write Iris tensor directory");
    std::ifstream input("weights.gguf", std::ios::binary);
    std::fstream output("iris-layout.gguf", std::ios::binary|std::ios::in|std::ios::out);
    input.exceptions(std::ios::failbit|std::ios::badbit);
    output.exceptions(std::ios::failbit|std::ios::badbit);
    constexpr int64_t chunk = 65536;
    std::vector<char> packed(1024*1024);
    std::vector<float> floats(chunk);
    std::vector<ggml_fp16_t> half(chunk);
    const auto data = gguf_get_meta_size(dst.get());
    for (int64_t i = 0; i < count; ++i) {
        const char *name = gguf_get_tensor_name(src.get(), i);
        input.seekg(gguf_get_data_offset(src.get()) + gguf_get_tensor_offset(src.get(), i));
        output.seekp(data + gguf_get_tensor_offset(dst.get(), i));
        if (!matrices.contains(name)) {
            size_t left = gguf_get_tensor_size(src.get(), i);
            while (left) {
                const auto n = std::min(left, packed.size());
                input.read(packed.data(), n);
                output.write(packed.data(), n);
                left -= n;
            }
        } else {
            const auto type = gguf_get_tensor_type(src.get(), i);
            const auto *traits = ggml_get_type_traits(type);
            if (!traits || (!traits->to_float && type != GGML_TYPE_F32))
                throw std::runtime_error("Unsupported packed Iris tensor type");
            int64_t left = ggml_nelements(ggml_get_tensor(tensors.get(), name));
            while (left) {
                const auto n = std::min(left, chunk);
                if (n % traits->blck_size) throw std::runtime_error("Incomplete Iris quantization block");
                const size_t bytes = (n / traits->blck_size) * traits->type_size;
                if (bytes > packed.size()) throw std::runtime_error("Invalid Iris tensor block size");
                input.read(packed.data(), bytes);
                if (type == GGML_TYPE_F32) std::memcpy(floats.data(), packed.data(), bytes);
                else traits->to_float(packed.data(), floats.data(), n);
                ggml_fp32_to_fp16_row(floats.data(), half.data(), n);
                output.write(reinterpret_cast<const char*>(half.data()), n*sizeof(ggml_fp16_t));
                left -= n;
            }
        }
        const auto alignment = gguf_get_alignment(dst.get());
        const auto pad = (alignment - gguf_get_tensor_size(dst.get(), i) % alignment) % alignment;
        for (size_t j = 0; j < pad; ++j) output.put(0);
    }
    output.close();
}
