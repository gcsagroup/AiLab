#pragma once
#ifdef _WIN32
#include <windows.h>
#include <cwctype>
#include <charconv>

static void mapped_check(BOOL ok, const char *action) {
    if (!ok) throw std::runtime_error(std::string(action) + " failed (" + std::to_string(GetLastError()) + ")");
}

static void apply_mapped_budget(HANDLE process, unsigned long long floor_bytes, unsigned long long requested) {
    MEMORYSTATUSEX mem{};
    mem.dwLength = sizeof(mem);
    mapped_check(GlobalMemoryStatusEx(&mem), "Physical memory query");
    constexpr unsigned long long reserve = 2ull << 30;
    const auto available = mem.ullAvailPhys > reserve ? mem.ullAvailPhys - reserve : 0ull;
    const auto limit = std::min(requested, (available >> 20) << 20);
    if (limit < floor_bytes) throw std::runtime_error("Insufficient physical memory for the mapped CPU layer");
    SIZE_T low = 0, high = 0;
    DWORD flags = 0;
    mapped_check(GetProcessWorkingSetSizeEx(process, &low, &high, &flags), "Query service working set");
    mapped_check(SetProcessWorkingSetSizeEx(process, low, static_cast<SIZE_T>(limit),
          QUOTA_LIMITS_HARDWS_MIN_DISABLE | QUOTA_LIMITS_HARDWS_MAX_ENABLE), "Bound service working set");
    mapped_check(GetProcessWorkingSetSizeEx(process, &low, &high, &flags), "Verify service working set");
    if (!(flags & QUOTA_LIMITS_HARDWS_MAX_ENABLE) || high > limit || high < floor_bytes)
        throw std::runtime_error("Windows did not apply the requested CPU working-set limit");
    std::cerr << "AiLab mapped CPU service resident limit " << (high >> 20) << " MiB\n";
}

// Keep the service in a private kill-on-close job and impose its resident
// working-set budget before any model code can run.
static int bounded_service(const char *floor_arg, const char *limit_arg) {
    auto mib = [](const char *s) {
        unsigned value = 0;
        const auto end = s + std::char_traits<char>::length(s);
        const auto res = std::from_chars(s, end, value);
        if (res.ec != std::errc{} || res.ptr != end || value == 0) throw std::runtime_error("Invalid memory limit");
        return static_cast<unsigned long long>(value) << 20;
    };
    const auto floor_bytes = mib(floor_arg), requested = mib(limit_arg);
    std::vector<wchar_t> self(32768);
    const DWORD n = GetModuleFileNameW(nullptr, self.data(), static_cast<DWORD>(self.size()));
    mapped_check(n && n < self.size(), "Worker path");
    const auto server = std::filesystem::path(self.data()).parent_path() / L"llama-server.exe";
    // Node quoted the original UTF-16 argument vector. Skip only our four
    // fixed prefix arguments, leaving all model paths and templates intact.
    auto tail = GetCommandLineW();
    for (int i=0; i<4; ++i) {
        while (*tail && std::iswspace(*tail)) ++tail;
        bool quoted = false;
        while (*tail && (quoted || !std::iswspace(*tail))) {
            if (*tail == L'"') quoted = !quoted;
            ++tail;
        }
    }
    std::wstring command = L"\"" + server.wstring() + L"\" " + tail;
    using handle = std::unique_ptr<void, decltype(&CloseHandle)>;
    handle job(CreateJobObjectW(nullptr, nullptr), CloseHandle);
    mapped_check(job != nullptr, "Create job");
    JOBOBJECT_EXTENDED_LIMIT_INFORMATION limits{};
    limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
    mapped_check(SetInformationJobObject(job.get(), JobObjectExtendedLimitInformation, &limits, sizeof(limits)), "Set job limits");
    SIZE_T storage = 0;
    InitializeProcThreadAttributeList(nullptr, 1, 0, &storage);
    std::vector<unsigned char> buffer(storage);
    auto attrs = reinterpret_cast<LPPROC_THREAD_ATTRIBUTE_LIST>(buffer.data());
    mapped_check(InitializeProcThreadAttributeList(attrs, 1, 0, &storage), "Initialize job attributes");
    std::unique_ptr<_PROC_THREAD_ATTRIBUTE_LIST, decltype(&DeleteProcThreadAttributeList)> attr_guard(attrs, DeleteProcThreadAttributeList);
    HANDLE job_handle = job.get();
    mapped_check(UpdateProcThreadAttribute(attrs, 0, PROC_THREAD_ATTRIBUTE_JOB_LIST, &job_handle, sizeof(job_handle), nullptr, nullptr), "Attach service job");
    STARTUPINFOEXW start{};
    start.StartupInfo.cb = sizeof(start);
    start.StartupInfo.dwFlags = STARTF_USESTDHANDLES;
    start.StartupInfo.hStdInput = GetStdHandle(STD_INPUT_HANDLE);
    start.StartupInfo.hStdOutput = GetStdHandle(STD_OUTPUT_HANDLE);
    start.StartupInfo.hStdError = GetStdHandle(STD_ERROR_HANDLE);
    start.lpAttributeList = attrs;
    PROCESS_INFORMATION pi{};
    mapped_check(CreateProcessW(server.c_str(), command.data(), nullptr, nullptr, TRUE,
          CREATE_SUSPENDED | CREATE_NO_WINDOW | EXTENDED_STARTUPINFO_PRESENT, nullptr, nullptr, &start.StartupInfo, &pi), "Create CPU service");
    handle process(pi.hProcess, CloseHandle), thread(pi.hThread, CloseHandle);
    apply_mapped_budget(process.get(), floor_bytes, requested);
    mapped_check(ResumeThread(thread.get()) != static_cast<DWORD>(-1), "Resume CPU service");
    mapped_check(WaitForSingleObject(process.get(), INFINITE) == WAIT_OBJECT_0, "Wait for CPU service");
    DWORD code = 1;
    mapped_check(GetExitCodeProcess(process.get(), &code), "CPU service exit status");
    return static_cast<int>(code);
}
#endif
