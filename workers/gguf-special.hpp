// Non-autoregressive GGUF graphs share the model and context configured by the worker.
static void append_piece(std::string &text,const llama_vocab *vocab,llama_token token) {
    std::vector<char> buf(64);
    int n=llama_token_to_piece(vocab,token,buf.data(),buf.size(),0,true);
    if (n<0) { buf.resize(-n); n=llama_token_to_piece(vocab,token,buf.data(),buf.size(),0,true); }
    if (n<0) throw std::runtime_error("无法解码词元。");
    text.append(buf.data(),n);
}

// Refine a block of masked tokens at a time. Every evaluation sees the full bidirectional sequence.
static void denoise(llama_context *ctx,const llama_vocab *vocab,std::vector<llama_token> tokens,
                    const json &r,unsigned limit,const std::string &arch) {
    const auto mask=llama_vocab_mask(vocab);
    if(mask==LLAMA_TOKEN_NULL) throw std::runtime_error("扩散模型缺少 mask 词元。");
    llama_set_causal_attn(ctx,false);
    std::unique_ptr<llama_sampler,decltype(&llama_sampler_free)> sampler(llama_sampler_chain_init(llama_sampler_chain_default_params()),llama_sampler_free);
    const float temp=r.at("temperature");
    if(temp==0) llama_sampler_chain_add(sampler.get(),llama_sampler_init_greedy());
    else {
        llama_sampler_chain_add(sampler.get(),llama_sampler_init_temp(temp));
        llama_sampler_chain_add(sampler.get(),llama_sampler_init_top_p(r.at("top_p"),1));
        llama_sampler_chain_add(sampler.get(),llama_sampler_init_dist(r.at("seed")));
    }
    const auto start=tokens.size();
    // Dream and RND1 train the previous position to predict each masked token.
    const bool rnd=arch=="rnd1";
    const bool shift_logits=rnd || arch=="dream";
    const auto logit_position=[shift_logits](size_t i){return shift_logits && i>0 ? i-1 : i;};
    tokens.resize(start+limit,mask);
    const size_t generation_end=tokens.size();
    // The published conditional sampler fixes EOS after the masked span.
    // Bidirectional attention can see that token at every denoising step.
    if (rnd && llama_vocab_eos(vocab)!=LLAMA_TOKEN_NULL) tokens.push_back(llama_vocab_eos(vocab));
    std::string pending,reason="length";
    unsigned generated=0;
    const auto stops=r.at("stop").get<std::vector<std::string>>();
    const int vocab_size=llama_vocab_n_tokens(vocab);
    std::vector<llama_token_data> distribution(vocab_size);
    auto batch=llama_batch_init(tokens.size(),0,1);
    struct FreeBatch {llama_batch &b; ~FreeBatch(){llama_batch_free(b);}} guard{batch};
    const size_t window=rnd ? std::max(1u,limit) : 32;
    for(size_t first=start;first<generation_end && reason=="length"; first+=window) {
        const size_t end=std::min(first+window,generation_end);
        size_t remaining=end-first;
        unsigned step=0;
        while(remaining) {
            batch.n_tokens=tokens.size();
            for(size_t i=0;i<tokens.size();++i) {
                batch.token[i]=tokens[i];batch.pos[i]=i;batch.n_seq_id[i]=1;batch.seq_id[i][0]=0;
                batch.logits[i]=0;
            }
            for(size_t i=first;i<end;++i) if(tokens[i]==mask) batch.logits[logit_position(i)]=1;
            if(auto mem=llama_get_memory(ctx)) llama_memory_clear(mem,true);
            if(llama_decode(ctx,batch)!=0) throw std::runtime_error("扩散去噪前向失败。");
            struct Guess {double confidence; size_t pos; llama_token token;};
            std::vector<Guess> guesses;
            for(size_t i=first;i<end;++i) if(tokens[i]==mask) {
                const auto logits=llama_get_logits_ith(ctx,logit_position(i));
                if(!logits) throw std::runtime_error("缺少掩码位置的 logits。");
                float peak=-INFINITY;
                for(int j=0;j<vocab_size;++j) if(j!=mask) peak=std::max(peak,logits[j]);
                if(!std::isfinite(peak)) throw std::runtime_error("扩散模型未给出有效的词元分数。");
                double mass=0,weighted=0;
                for(int j=0;j<vocab_size;++j) {
                    distribution[j]={j,j==mask?-INFINITY:logits[j],0};
                    if(j!=mask && std::isfinite(logits[j])) {
                        const double delta=double(logits[j]-peak);
                        const double weight=std::exp(delta);
                        mass+=weight;
                        if(rnd && temp==0) weighted+=delta*weight;
                    }
                }
                llama_token_data_array candidates{distribution.data(),distribution.size(),-1,false};
                llama_sampler_apply(sampler.get(),&candidates);
                const auto next=candidates.data[candidates.selected].id;
                double score=std::exp(double(logits[next]-peak))/mass;
                if(rnd) {
                    // RND1 leaves high-entropy positions masked. With greedy
                    // token selection, rank positions by the unscaled logits.
                    if(temp==0) score=weighted/mass-std::log(mass);
                    else {
                        score=0;
                        for(size_t j=0;j<candidates.size;++j) {
                            const double p=candidates.data[j].p;
                            if(p>0) score+=p*std::log(p);
                        }
                    }
                }
                guesses.push_back({score,i,next});
            }
            std::stable_sort(guesses.begin(),guesses.end(),[](const Guess&a,const Guess&b){return a.confidence>b.confidence;});
            size_t update=std::min(remaining,(end-first+7)/8);
            if(rnd) {
                const size_t count=end-first,already=count-remaining;
                do {++step;} while((count*step+255)/256<=already);
                update=(count*step+255)/256-already;
            }
            for(size_t j=0;j<update;++j) tokens[guesses[j].pos]=guesses[j].token;
            remaining-=update;
        }
        for(size_t i=first;i<end;++i) {
            if(llama_vocab_is_eog(vocab,tokens[i])) {reason="eos";break;}
            ++generated; append_piece(pending,vocab,tokens[i]);
            if(flush_visible(pending,stops,false)) {reason="stop";break;}
        }
    }
    if(reason!="stop") flush_visible(pending,stops,true);
    emit({{"type","done"},{"finish_reason",reason},{"completion_tokens",generated}});
}

// WavTokenizer Vocos output is a 1280-point log-magnitude/phase STFT, 320 samples per code.
static void decode_codes(llama_context *ctx,const llama_model *model,std::vector<llama_token> &codes,const std::string &output) {
    constexpr int fft=1280,bins=fft/2+1,hop=320,pad=(fft-hop)/2;
    if(llama_model_n_embd_out(model)!=2*bins) throw std::runtime_error("无法识别声码器频谱尺寸。");
    auto batch=llama_batch_get_one(codes.data(),codes.size());
    std::vector<int8_t> all(codes.size(),1);batch.logits=all.data();
    if(llama_encode(ctx,batch)!=0) throw std::runtime_error("声码器计算失败。");
    std::vector<double> sum(codes.size()*hop+2*pad),window_sum(sum.size()),window(fft),cosine(fft),sine(fft);
    const double tau=2*std::acos(-1.);
    for(int i=0;i<fft;++i) {
        cosine[i]=std::cos(tau*i/fft);sine[i]=std::sin(tau*i/fft);window[i]=(1-cosine[i])*0.5;
    }
    for(size_t frame=0;frame<codes.size();++frame) {
        auto spec=llama_get_embeddings_ith(ctx,frame);
        if(!spec) throw std::runtime_error("声码器缺少频谱输出。");
        std::vector<double> re(bins),im(bins);
        for(int k=0;k<bins;++k){
            const double mag=std::exp(std::min(double(spec[k]),std::log(100.0)));
            const double gain=(k==0 || k==bins-1)?1:2;
            re[k]=gain*mag*std::cos(spec[k+bins]);im[k]=gain*mag*std::sin(spec[k+bins]);
        }
        for(int t=0;t<fft;++t) {
            double sample=0;int phase=0;
            for(int k=0;k<bins;++k) {
                sample+=re[k]*cosine[phase]-im[k]*sine[phase];
                phase+=t;if(phase>=fft)phase-=fft;
            }
            const size_t pos=frame*hop+t;
            sum[pos]+=sample*window[t]/fft;window_sum[pos]+=window[t]*window[t];
        }
    }
    std::ofstream wav(std::filesystem::u8path(output),std::ios::binary);
    auto field=[&](uint32_t value,int bytes){for(int i=0;i<bytes;++i)wav.put(static_cast<char>(value>>(8*i)));};
    const auto size=codes.size()*hop*2;
    wav.write("RIFF",4);field(size+36,4);wav.write("WAVEfmt ",8);field(16,4);field(1,2);field(1,2);
    field(24000,4);field(48000,4);field(2,2);field(16,2);wav.write("data",4);field(size,4);
    for(size_t i=pad;i<sum.size()-pad;++i){
        const auto sample=sum[i]/std::max(1e-10,window_sum[i]);
        if(!std::isfinite(sample))throw std::runtime_error("声码器输出无效。");
        field(static_cast<uint16_t>(std::lround(std::clamp(sample,-1.,1.)*32767)),2);
    }
    wav.close();if(!wav)throw std::runtime_error("无法保存声码器 WAV。");
    emit({{"type","done"},{"finish_reason","audio"},{"samples",size/2}});
}
