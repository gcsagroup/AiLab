// Image and image-conditioned video share the same compiled stable-diffusion.cpp backend.
#include "stable-diffusion.h"
#define STB_IMAGE_WRITE_IMPLEMENTATION
#include "stb_image_write.h"
#include <nlohmann/json.hpp>
#include <cstring>
#include <chrono>
#include <map>
#include <fstream>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

using json = nlohmann::json;
static void check(sd_status_t status) {
    if (status != SD_STATUS_OK) {
        const char* why = sd_get_last_error();
        throw std::runtime_error(why && *why ? why : "Diffusion graph failed");
    }
}
static void log_message(sd_log_level_t level, const char* message, void*) {
    if (message && level >= SD_LOG_WARN) std::cerr << message << std::endl;
}
using Clock = std::chrono::steady_clock;
struct GenerationTiming {
    Clock::time_point since;
    std::string stage;
    std::map<std::string, double> elapsed;
    int64_t sampling_steps = 0, last_step = 0;
    int last_pass = -1;
    void change(const std::string& next) {
        if (next == stage) return;
        const auto now = Clock::now();
        if (!stage.empty()) elapsed[stage] += std::chrono::duration<double,std::milli>(now-since).count();
        since = now; stage = next;
    }
};
static void progress(const sd_generation_progress_t* state, void* data) {
    if (!state || !state->stage) return;
    auto& timing = *static_cast<GenerationTiming*>(data);
    timing.change(state->stage);
    if (timing.stage != "sampling") return;
    if (timing.last_pass != state->sample_pass || state->completed < timing.last_step) timing.last_step = 0;
    timing.sampling_steps += state->completed - timing.last_step;
    timing.last_step = state->completed;
    timing.last_pass = state->sample_pass;
    const double elapsed=timing.elapsed["sampling"]+std::chrono::duration<double,std::milli>(Clock::now()-timing.since).count();
    std::cout << json{{"type", "step"}, {"completed", state->completed}, {"total", state->total},
        {"sampling_ms",elapsed},{"sampling_steps",timing.sampling_steps}} << std::endl;
}
static void condition_video(sd_opt_t* options, int width, int height) {
    const int64_t shape[] = {3, width, height};
    std::vector<char> rgb(3 * width * height);
    std::ifstream input("condition.rgb", std::ios::binary);
    if (!input.read(rgb.data(), rgb.size()) || input.peek() != std::ifstream::traits_type::eof())
        throw std::runtime_error("Invalid RGB conditioning image");
    std::unique_ptr<sd_tensor_t, decltype(&sd_tensor_free)> pixels(
        sd_tensor_create(SD_TENSOR_U8, 3, shape, rgb.data(), rgb.size()), sd_tensor_free);
    if (!pixels) throw std::runtime_error("Cannot create conditioning tensor");
    check(sd_opt_set_tensor(options, "init_image", pixels.get()));
}
static void generate(const json& request) {
    const bool video = request.value("kind", std::string("image")) == "video";
    const auto& r = request.at("runtime");
    const auto& input = request.at("input");
    const auto pipeline = r.value("pipeline",std::string());
    const bool h3 = pipeline=="h3-image" || pipeline=="h3-video";
    const bool z_image = !video && pipeline=="z-image";
    const int width = video ? r.at("inference_width").get<int>() : 512;
    const int height = video ? r.at("inference_height").get<int>() : 512;
    if (video && (width != 512 || height != 320)) throw std::runtime_error("Unexpected video inference size");
    const int steps = r.at("steps").get<int>();
    const int frames = video ? r.at("frames").get<int>() : 1;
    auto context = std::unique_ptr<sd_opt_t, decltype(&sd_opt_free)>(sd_ctx_opt_create(), sd_opt_free);
    auto options = std::unique_ptr<sd_opt_t, decltype(&sd_opt_free)>(
        video ? sd_vid_gen_opt_create() : sd_img_gen_opt_create(), sd_opt_free);
    if (!context || !options) throw std::runtime_error("Cannot allocate diffusion options");
    auto device = r.at("device_id").get<std::string>();
    for (char& c : device) if (c >= 'A' && c <= 'Z') c += 'a' - 'A';
    check(sd_opt_set_string(context.get(), (h3 || z_image) ? "diffusion_model_path" : "model_path", "weights.gguf"));
    if (z_image) {
        check(sd_opt_set_string(context.get(), "llm_path", "qwen3_encoder.gguf"));
        check(sd_opt_set_string(context.get(), "vae_path", "flux_vae.gguf"));
        check(sd_opt_set_bool(context.get(), "enable_mmap", true));
    }
    if (h3) {
        check(sd_opt_set_string(context.get(), "rng_type", "cpu"));
        check(sd_opt_set_string(context.get(),"llm_path","encoder.gguf"));
        check(sd_opt_set_string(context.get(),"vae_path",video ? "video_vae.gguf" : "image_vae.gguf"));
        if (request.value("has_audio",false)) check(sd_opt_set_string(context.get(),"audio_vae_path","audio_vae.gguf"));
        check(sd_opt_set_bool(context.get(),"enable_mmap",true));
        if (r.contains("vram_budget_gib")) {
            const auto budget=std::to_string(r.at("vram_budget_gib").get<double>());
            check(sd_opt_set_string(context.get(),"max_vram",budget.c_str()));
        }
        check(sd_opt_set_bool(context.get(),"diffusion_flash_attn",true));
        check(sd_opt_set_string(options.get(),"sample.method","euler"));
        if (!video && steps==6) {
            const float sigmas[]={1.f,.967523694f,.887548506f,.75f,.532773912f,.232008874f,0.f};
            check(sd_opt_set_floats(options.get(),"sample.sigmas",sigmas,7));
        }
    }
    const auto backend = h3 ? r.value("diffusion_placement", device) : device;
    check(sd_opt_set_string(context.get(), "backend", backend.c_str()));
    check(sd_opt_set_string(context.get(), "params_backend", "cpu"));
    check(sd_opt_set_int(context.get(), "n_threads", 6));
    if (video && !h3) {
        check(sd_opt_set_string(context.get(), "motion_module_path", "motion.gguf"));
        check(sd_opt_set_bool(context.get(), "diffusion_flash_attn", true));
    }
    sd_ctx_t* raw_ctx = nullptr;
    const auto load_started = Clock::now();
    check(sd_ctx_create(context.get(), &raw_ctx));
    std::cout << json{{"type","timing"},{"model_load_ms",std::chrono::duration<double,std::milli>(Clock::now()-load_started).count()}} << std::endl;
    GenerationTiming timing{};
    std::unique_ptr<sd_ctx_t, decltype(&sd_ctx_free)> ctx(raw_ctx, sd_ctx_free);
    if (!(video ? sd_ctx_supports_video_generation(ctx.get()) : sd_ctx_supports_image_generation(ctx.get())))
        throw std::runtime_error("GGUF weights do not provide the requested diffusion graph");
    sd_set_generation_progress_callback(ctx.get(), progress, &timing);
    const auto prompt = input.value("prompt", std::string());
    const auto negative = input.value("negative_prompt", std::string());
    check(sd_opt_set_string(options.get(), "prompt", prompt.c_str()));
    check(sd_opt_set_string(options.get(), "negative_prompt", negative.c_str()));
    check(sd_opt_set_int(options.get(), "width", width));
    check(sd_opt_set_int(options.get(), "height", height));
    check(sd_opt_set_int(options.get(), "seed", r.at("seed").get<int64_t>()));
    check(sd_opt_set_int(options.get(), "sample.steps", steps));
    check(sd_opt_set_float(options.get(), "sample.guidance.txt_cfg", video ? 1.0 : r.at("cfg").get<double>()));
    check(sd_opt_set_bool(options.get(), "vae_tiling.enabled", true));
    if (video) {
        check(sd_opt_set_int(options.get(), "video_frames", frames));
        check(sd_opt_set_int(options.get(), "fps", r.at("fps").get<int>()));
        if (!h3) check(sd_opt_set_float(options.get(), "strength", r.at("strength").get<double>()));
        if (request.value("has_image",true)) condition_video(options.get(), width, height);
    }
    sd_result_t* raw = nullptr;
    check(video ? sd_generate_video(ctx.get(), options.get(), &raw) : sd_generate_image(ctx.get(), options.get(), &raw));
    timing.change("");
    json measured={{"type","timing"},{"sampling_steps",timing.sampling_steps}};
    for (const auto& [stage, ms] : timing.elapsed) measured[stage+"_ms"]=ms;
    std::cout << measured << std::endl;
    std::unique_ptr<sd_result_t, decltype(&sd_result_free)> result(raw, sd_result_free);
    if (video) {
        const auto* clip = sd_result_get_video(result.get());
        const auto* pixels = clip ? clip->data : nullptr;
        if (!pixels || clip->fps != r.at("fps").get<int>() || sd_tensor_type(pixels) != SD_TENSOR_U8 ||
            sd_tensor_rank(pixels) != 4 || sd_tensor_dim(pixels, 0) != 3 || sd_tensor_dim(pixels, 1) != width ||
            sd_tensor_dim(pixels, 2) != height || sd_tensor_dim(pixels, 3) != frames)
            throw std::runtime_error("Unexpected video graph output " + std::to_string(sd_result_get_image_count(result.get())) +
                " frames at " + std::to_string(sd_result_get_fps(result.get())) + " fps, tensor " +
                (pixels ? std::to_string(sd_tensor_dim(pixels, 0)) + " x " + std::to_string(sd_tensor_dim(pixels, 1)) +
                  " x " + std::to_string(sd_tensor_dim(pixels, 2)) + " x " + std::to_string(sd_tensor_dim(pixels, 3)) : "missing"));
        std::ofstream output("frames.rgb", std::ios::binary);
        output.write(static_cast<const char*>(sd_tensor_data(pixels)), sd_tensor_byte_size(pixels));
        output.close();
        if (!output) throw std::runtime_error("Video frame write failed");
        if (request.value("has_audio",false)) {
            const auto* audio=sd_result_get_audio(result.get());
            const auto* pcm=audio ? audio->data : nullptr;
            if(!pcm || sd_tensor_type(pcm)!=SD_TENSOR_F32 || sd_tensor_rank(pcm)!=2 || !sd_tensor_byte_size(pcm))
                throw std::runtime_error("H3 returned no decoded audio");
            std::ofstream sound("audio.f32",std::ios::binary), meta("audio.json");
            sound.write(static_cast<const char*>(sd_tensor_data(pcm)),sd_tensor_byte_size(pcm));
            meta << json{{"rate",audio->sample_rate},{"channels",sd_tensor_dim(pcm,0)}};
            sound.close(); meta.close();
            if(!sound || !meta) throw std::runtime_error("H3 audio write failed");
        }
    } else {
        const auto* pixels = sd_result_get_image(result.get(), 0);
        if (!pixels || sd_result_get_image_count(result.get()) != 1 || sd_tensor_type(pixels) != SD_TENSOR_U8 ||
            sd_tensor_rank(pixels) != 3 || sd_tensor_dim(pixels, 1) != width || sd_tensor_dim(pixels, 2) != height)
            throw std::runtime_error("Invalid image graph output");
        const int channels = sd_tensor_dim(pixels, 0);
        if ((channels != 3 && channels != 4) ||
            !stbi_write_png("image.png", width, height, channels, sd_tensor_data(pixels), width * channels))
            throw std::runtime_error("PNG write failed");
    }
}
int main() {
    try {
        std::string line;
        std::getline(std::cin, line);
        sd_set_log_callback(log_message, nullptr);
        const auto request = json::parse(line);
        if (request.value("action", std::string()) == "probe") {
            std::unique_ptr<sd_opt_t, decltype(&sd_opt_free)> context(sd_ctx_opt_create(), sd_opt_free),
                image(sd_img_gen_opt_create(), sd_opt_free), video(sd_vid_gen_opt_create(), sd_opt_free);
            if (!context || !image || !video) throw std::runtime_error("Cannot initialize diffusion options");
            check(sd_opt_set_string(context.get(), "rng_type", "cpu"));
            std::cout << json{{"type", "diffusion_ready"}} << std::endl;
        } else {
            generate(request);
        }
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << std::endl;
        return 1;
    }
}
