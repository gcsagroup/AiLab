#pragma once
#include "gguf.h"
#include <array>
#include <map>

// ZAYA's early GGUF releases split each transformer layer into an attention
// block followed by a MoE block. Move residuals from pre-block to post-block,
// as in the publisher's layout and llama.cpp's mainline zaya1 converter.
static void prepare_zaya(const std::string &source, const std::string &dest) {
    using Gguf = std::unique_ptr<gguf_context, decltype(&gguf_free)>;
    Gguf src(gguf_init_from_file(source.c_str(), {true,nullptr}),gguf_free);
    Gguf dst(gguf_init_empty(),gguf_free);
    if (!src || !dst) throw std::runtime_error("Cannot read the ZAYA GGUF directory");
    auto require = [](bool ok,const std::string &field) {
        if (!ok) throw std::runtime_error("Unsupported legacy ZAYA layout: " + field);
    };
    auto key = [&](std::string name) {
        auto id = gguf_find_key(src.get(),name.c_str());
        require(id>=0,name); return id;
    };
    auto number = [&](const std::string &name) -> double {
        auto id=key("zaya."+name);
        switch (gguf_get_kv_type(src.get(),id)) {
            case GGUF_TYPE_UINT32: return gguf_get_val_u32(src.get(),id);
            case GGUF_TYPE_INT32: return gguf_get_val_i32(src.get(),id);
            case GGUF_TYPE_FLOAT32: return gguf_get_val_f32(src.get(),id);
            default: throw std::runtime_error("Invalid numeric ZAYA hyperparameter: "+name);
        }
    };
    require(gguf_get_kv_type(src.get(),key("general.architecture"))==GGUF_TYPE_STRING &&
        std::string(gguf_get_val_str(src.get(),key("general.architecture")))=="zaya","general.architecture");
    const int blocks=number("block_count"), embedding=number("embedding_length");
    const int heads=number("attention.head_count"), kv=number("attention.head_count_kv");
    const int head=number("attention.key_length"), groups=heads+kv;
    require(blocks>=2 && blocks<=512 && !(blocks%2) && embedding>0 && embedding<=16384,"block_count or embedding_length");
    require(kv==2 && heads>0 && heads<=128 && head>0 && head<=512 &&
            number("attention.value_length")==head && number("ssm.conv_kernel")==2,"CCA dimensions");
    const int layers=blocks/2;
    const auto count=gguf_get_n_tensors(src.get());
    require(count>0 && count<=65536,"tensor count");
    std::vector<bool> used(count);
    auto tensor = [&](const std::string &name) {
        const auto id=gguf_find_tensor(src.get(),name.c_str());
        require(id>=0,name);
        used[id]=true;
        return id;
    };
    auto dims=[&](int64_t id) {
        const auto *ne=gguf_get_tensor_ne(src.get(),id);
        return std::array<int64_t,4>{ne[0],ne[1],ne[2],ne[3]};
    };
    const auto tokens=key("tokenizer.ggml.tokens");
    require(gguf_get_kv_type(src.get(),tokens)==GGUF_TYPE_ARRAY &&
            gguf_get_arr_type(src.get(),tokens)==GGUF_TYPE_STRING,"tokenizer.ggml.tokens");
    const int64_t emb=tensor("token_embd.weight"), vocabulary=gguf_get_arr_n(src.get(),tokens);
    require(dims(emb)[0]==embedding && dims(emb)[1]==vocabulary,"embedding and vocabulary");
    const auto down=dims(tensor("blk.1.ffn_down_exps.weight"));
    const auto router=dims(tensor("blk.1.ffn_gate_inp.weight"));
    require(down[0]>0 && down[1]==embedding && down[2]==number("expert_count") &&
            router[0]==embedding && router[1]>0 && router[1]<=8192 && number("expert_used_count")==1,"expert dimensions");

    gguf_set_kv(dst.get(),src.get());
    for (int64_t i=0;i<gguf_get_n_kv(src.get());++i) {
        const char *k=gguf_get_key(src.get(),i);
        if (std::string(k).rfind("zaya.",0)==0) gguf_remove_key(dst.get(),k);
    }
    gguf_set_val_str(dst.get(),"general.architecture","zaya1");
    auto u32=[&](const std::string &name,int64_t n) {
        require(n>0 && n<=UINT32_MAX,name);
        gguf_set_val_u32(dst.get(),("zaya1."+name).c_str(),static_cast<uint32_t>(n));
    };
    for (auto k:{"context_length","embedding_length","feed_forward_length","attention.head_count","attention.head_count_kv",
                 "attention.key_length","attention.value_length","rope.dimension_count","ssm.conv_kernel","expert_count","expert_used_count"})
        u32(k,number(k));
    u32("block_count",layers); u32("vocab_size",vocabulary);
    u32("router_hidden_size",router[1]); u32("expert_feed_forward_length",down[0]);
    for (auto k:{"rope.freq_base","attention.layer_norm_rms_epsilon"})
        gguf_set_val_f32(dst.get(),(std::string("zaya1.")+k).c_str(),static_cast<float>(number(k)));

    using Shape=std::array<int64_t,4>;
    using Ggml=std::unique_ptr<ggml_context, decltype(&ggml_free)>;
    Ggml arena(ggml_init({ggml_tensor_overhead()*static_cast<size_t>(count+64),nullptr,true}),ggml_free);
    require(!!arena,"GGML directory");
    enum class Op {copy, concat, floating, convolution, bias};
    struct Piece {Op op; std::vector<int64_t> sources;};
    std::vector<Piece> pieces;
    auto add=[&](std::string name,enum ggml_type type,Shape shape,Op op,std::vector<int64_t> ids) {
        require(gguf_find_tensor(dst.get(),name.c_str())<0,name);
        require(shape[0]>0 && shape[0]%ggml_blck_size(type)==0,name);
        auto *t=ggml_new_tensor(arena.get(),type,4,shape.data());
        ggml_set_name(t,name.c_str()); gguf_add_tensor(dst.get(),t);
        pieces.push_back({op,std::move(ids)});
    };
    auto copy=[&](const std::string &to,const std::string &from) {
        const auto i=tensor(from);
        add(to,gguf_get_tensor_type(src.get(),i),dims(i),Op::copy,{i});
    };
    copy("token_embd.weight","token_embd.weight"); copy("output_norm.weight","output_norm.weight");
    if (gguf_find_tensor(src.get(),"output.weight")>=0) copy("output.weight","output.weight");
    copy("res_scale_in.weight","blk.0.res_scale_hs.weight");
    copy("res_scale_in.bias","blk.0.res_scale_hs.bias");
    for (int i=0;i<layers;i++) {
        auto prefix=[](int n){return "blk."+std::to_string(n)+".";};
        const auto current=prefix(i), attention=prefix(2*i), ffn=prefix(2*i+1);
        for (auto name:{"attn_norm.weight","attn_q.weight","attn_k.weight","attn_output.weight","ssm_conv1d.weight",
                        "ssm_conv1d.bias","cca_conv_grp.bias"}) copy(current+name,attention+name);
        copy(current+"cca_temp.weight",attention+"cca_k_scale.weight");
        const auto v1=tensor(attention+"cca_val_proj1.weight"),v2=tensor(attention+"cca_val_proj2.weight");
        require(dims(v1)==Shape{embedding,head,1,1} && dims(v2)==dims(v1) &&
                gguf_get_tensor_type(src.get(),v1)==gguf_get_tensor_type(src.get(),v2),"value projections");
        add(current+"attn_v.weight",gguf_get_tensor_type(src.get(),v1),{embedding,2*head,1,1},Op::concat,{v1,v2});
        const auto conv=tensor(attention+"cca_conv_grp.weight");
        require(dims(conv)==Shape{2,head,groups*head,1},"grouped convolution");
        add(current+"cca_conv_grp.weight",GGML_TYPE_F32,{head,head,groups,2},Op::convolution,{conv});
        copy(current+"ffn_norm.weight",ffn+"attn_norm.weight");
        for (auto name:{"ffn_gate_inp.weight","ffn_gate_inp.bias","ffn_gate_up_exps.weight","ffn_down_exps.weight"})
            copy(current+name,ffn+name);
        copy(current+"ffn_router_norm.weight",ffn+"ffn_norm.weight");
        copy(current+"exp_probs_b.bias",ffn+"zaya_router_biases.weight");
        if (i) copy(current+"ffn_router_eda.weight",ffn+"zaya_router_eda.weight");
        for (const auto &pair:std::map<std::string,std::string>{{"ffn_router_fc1","ffn_gate"},
                {"ffn_router_fc2","zaya_router_mlp2"},{"ffn_router_out","zaya_router_mlp4"}}) {
            const auto t=tensor(ffn+pair.second+".weight");
            add(current+pair.first+".weight",GGML_TYPE_F32,dims(t),Op::floating,{t});
            if (pair.first!="ffn_router_out") copy(current+pair.first+".bias",ffn+pair.second+".bias");
        }
        auto residual=[&](const std::string &where,const std::string &input) {
            const auto h=tensor(input+"res_scale_hs.weight"), hb=tensor(input+"res_scale_hs.bias");
            const auto r=tensor(input+"res_scale_res.weight"), rb=tensor(input+"res_scale_res.bias");
            for (auto q:{h,hb,r,rb}) require(dims(q)==Shape{embedding,1,1,1},"residual dimensions");
            copy(current+where+"_res_scale_hs.weight",input+"res_scale_hs.weight");
            copy(current+where+"_resid_scale.weight",input+"res_scale_res.weight");
            add(current+where+"_resid_scale.bias",GGML_TYPE_F32,{embedding,1,1,1},Op::bias,{h,hb,r,rb});
        };
        residual("attn",ffn);
        residual("ffn",i+1<layers ? prefix(2*i+2) : "");
    }
    for (int64_t i=0;i<count;i++) require(used[i],gguf_get_tensor_name(src.get(),i));
    const auto base=gguf_get_data_offset(src.get()),header=gguf_get_meta_size(dst.get());
    const auto last=pieces.size()-1,alignment=gguf_get_alignment(dst.get());
    const size_t need=header+gguf_get_tensor_offset(dst.get(),last)+gguf_get_tensor_size(dst.get(),last)+alignment;
    const auto path=std::filesystem::u8path(dest);
    require(!std::filesystem::exists(path),"output already exists");
    if (std::filesystem::space(path.parent_path()).available<need+64*1024*1024)
        throw std::runtime_error("ZAYA 首次试用需要额外 "+std::to_string((need+1024*1024-1)/(1024*1024))+" MiB 磁盘空间。");
    std::ifstream input(std::filesystem::u8path(source),std::ios::binary);
    std::ofstream output(path,std::ios::binary);
    input.exceptions(std::ios::failbit|std::ios::badbit);output.exceptions(std::ios::failbit|std::ios::badbit);
    { std::vector<char> buf(header);gguf_get_meta_data(dst.get(),buf.data());output.write(buf.data(),buf.size()); }
    auto seek=[&](int64_t t){input.seekg(base+gguf_get_tensor_offset(src.get(),t));};
    auto floats=[&](int64_t t) {
        const auto n=dims(t);int64_t length=1;
        for (auto dim:n) {require(dim>0 && dim<=32*1024*1024/length,"working buffer"); length*=dim;}
        const size_t bytes=gguf_get_tensor_size(src.get(),t); require(bytes<=128*1024*1024,"working buffer");
        auto type=gguf_get_tensor_type(src.get(),t);
        std::vector<float> values(length);seek(t);
        if (type==GGML_TYPE_F32) input.read(reinterpret_cast<char*>(values.data()),length*sizeof(float));
        else {
            const auto *traits=ggml_get_type_traits(type);
            require(traits && traits->to_float,"conversion type");
            std::vector<char> packed(bytes);input.read(packed.data(),bytes);
            traits->to_float(packed.data(),values.data(),length);
        }
        return values;
    };
    std::vector<char> buffer(4*1024*1024),zeros(alignment);
    for (size_t i=0;i<pieces.size();++i) {
        const auto &piece=pieces[i];const auto &ids=piece.sources;
        const size_t start=header+gguf_get_tensor_offset(dst.get(),i),size=gguf_get_tensor_size(dst.get(),i);
        require(static_cast<size_t>(output.tellp())==start,"output offset");
        if (piece.op==Op::copy || piece.op==Op::concat) {
            for (auto id:ids) {
                seek(id);
                for (size_t left=gguf_get_tensor_size(src.get(),id);left;) {
                    const auto n=std::min(left,buffer.size());
                    input.read(buffer.data(),n);output.write(buffer.data(),n);left-=n;
                }
            }
        } else {
            auto values=floats(ids[0]);
            if (piece.op==Op::convolution) {
                const auto original=values;
                for (size_t j=0;j<values.size();j++) values[j/2+(j%2)*(values.size()/2)]=original[j];
            } else if (piece.op==Op::bias) {
                const auto hb=floats(ids[1]),r=floats(ids[2]),rb=floats(ids[3]);
                for (size_t j=0;j<values.size();j++) values[j]=hb[j]*values[j]+rb[j]*r[j];
            }
            output.write(reinterpret_cast<const char*>(values.data()),values.size()*sizeof(float));
        }
        require(static_cast<size_t>(output.tellp())==start+size,"output tensor size");
        output.write(zeros.data(),(alignment-size%alignment)%alignment);
    }
    output.close();emit({{"type","converted"},{"architecture","zaya1"},{"layers",layers}});
}
