#pragma once

// CogVLM uses sequential KV slots but gives every interior image patch the
// same rotary position. The last visual embedding uses the language experts.
struct cogvlm_attention {
    std::vector<llama_pos> positions;
    llama_pos image_end = 0;
    const float * end_embedding = nullptr;
    size_t width = 0;
    bool position_set = false;
    bool embedding_set = false;

    static bool observe(ggml_tensor *node, bool ask, void *user) {
        auto &st=*static_cast<cogvlm_attention *>(user);
        if (st.positions.empty()) return false;
        if (ask && node->op==GGML_OP_ROPE && !st.position_set) {
            auto *input=node->src[1];
            if (input && input->type==GGML_TYPE_I32 && ggml_nbytes(input)==st.positions.size()*sizeof(llama_pos)) {
                ggml_backend_tensor_set(input,st.positions.data(),0,ggml_nbytes(input));
                st.position_set=true;
            }
        }
        if (!st.end_embedding || node->op!=GGML_OP_GET_ROWS || !node->src[0] ||
            std::string(ggml_get_name(node->src[0]))!="token_embd.weight" ||
            node->type!=GGML_TYPE_F32 || ggml_nelements(node)!=static_cast<int64_t>(st.width)) return false;
        if (!ask) {
            ggml_backend_tensor_set(node,st.end_embedding,0,st.width*sizeof(float));
            st.embedding_set=true;
        }
        return true;
    }
    void decode(llama_context *ctx, llama_batch batch, llama_pos start, const float *eoi=nullptr) {
        const auto count=static_cast<size_t>(batch.n_tokens);
        std::vector<llama_pos> slots(count);
        positions.resize(count);
        for(size_t i=0;i<count;++i) {
            const llama_pos p=start+static_cast<llama_pos>(i);
            slots[i]=p;
            positions[i]=p<=1 ? p : p<image_end ? 2 : p-image_end+3;
        }
        batch.pos=slots.data();
        position_set=embedding_set=false;
        end_embedding=eoi;
        if(llama_decode(ctx,batch)!=0) throw std::runtime_error("CogVLM CPU 解码失败。");
        llama_synchronize(ctx);
        if(!position_set || (eoi && !embedding_set)) throw std::runtime_error("CogVLM 计算图未应用图像位置或结束嵌入。");
        end_embedding=nullptr;
        positions.clear();
    }
};

static int cogvlm_image_prefill(cogvlm_attention &state, llama_context *ctx, mtmd_context *vision,
                                const mtmd_input_chunk *image, llama_token bos,
                                std::vector<llama_token> &question, unsigned batch_size, llama_pos &next) {
    const size_t count=mtmd_input_chunk_get_n_tokens(image);
    if(count<3 || mtmd_encode_chunk(vision,image)!=0) throw std::runtime_error("CogVLM 图像编码失败。");
    float *features=mtmd_get_output_embd(vision);
    if(!features || bos==LLAMA_TOKEN_NULL) throw std::runtime_error("缺少 CogVLM 图像嵌入或 BOS。");
    state.image_end=static_cast<llama_pos>(count);
    state.decode(ctx,llama_batch_get_one(&bos,1),0);
    int chunks=1;
    next=1;
    for(size_t pos=0;pos<count-1;) {
        const size_t n=std::min<size_t>(batch_size,count-1-pos);
        llama_batch batch{};
        batch.n_tokens=static_cast<int32_t>(n);
        batch.embd=features+pos*state.width;
        state.decode(ctx,batch,next);
        next+=n;
        pos+=n;
        ++chunks;
    }
    // A token batch selects the language expert graph. Its embedding lookup is
    // replaced for this one row with the projector's learned EOI embedding.
    state.decode(ctx,llama_batch_get_one(&bos,1),next++,features+(count-1)*state.width);
    ++chunks;
    for(size_t i=0;i<question.size();i+=batch_size) {
        const size_t n=std::min<size_t>(batch_size,question.size()-i);
        state.decode(ctx,llama_batch_get_one(question.data()+i,n),next);
        next+=n;
        ++chunks;
    }
    return chunks;
}
