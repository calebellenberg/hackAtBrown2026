#include <smartspectra/container/foreground_container.hpp>
#include <smartspectra/container/settings.hpp>
#include <physiology/modules/messages/metrics.h>
#include <physiology/modules/messages/status.h>
#include <glog/logging.h>
#include <iostream>
#include <cstdio>
#include <cstdlib>

using namespace presage::smartspectra;


int main(int argc, char** argv) {
    google::InitGoogleLogging(argv[0]);
    FLAGS_alsologtostderr = true;
    setbuf(stdout, NULL); // Disable output buffering

    // 1. Get API Key
    std::string api_key;
    if (const char* env_key = std::getenv("SMARTSPECTRA_API_KEY")) {
        api_key = env_key;
    } else if (argc > 1) {
        api_key = argv[1];
    } else {
        std::cerr << "Error: No API Key provided.\n";
        return 1;
    }

    // 2. Get Frame Directory (for file stream input)
    std::string frame_dir = "/tmp/presage_frames";
    if (const char* env_dir = std::getenv("FRAME_DIR")) {
        frame_dir = env_dir;
    }
    
    // Construct file stream path pattern (19-digit microsecond timestamp)
    std::string file_stream_path = frame_dir + "/frame0000000000000000000.jpg";
    std::cerr << "Reading frames from: " << frame_dir << "\n";

    // 3. Settings
    container::settings::Settings<
        container::settings::OperationMode::Continuous,
        container::settings::IntegrationMode::Rest
    > settings;

    // File Stream Setup (reads timestamped images from directory)
    settings.video_source.file_stream_path = file_stream_path;
    settings.video_source.erase_read_files = true;  // Clean up processed frames
    settings.video_source.rescan_retry_delay_ms = 5;   // Faster poll for new frames
    settings.video_source.loop = false;
    
    // Buffer duration: 1.0s - breathing needs longer window for accurate detection
    settings.continuous.preprocessed_data_buffer_duration_s = 1.0;

    settings.headless = true;
    settings.interframe_delay_ms = 20;  // Default - aggressive values hurt breathing
    settings.integration.api_key = api_key;

    auto container = std::make_unique<container::CpuContinuousRestForegroundContainer>(settings);

    // Core Metrics Callback - pulse and breathing
    auto status = container->SetOnCoreMetricsOutput(
        [](const presage::physiology::MetricsBuffer& metrics, int64_t timestamp) {
            float pulse = 0.0f;
            float breathing = 0.0f;

            if (!metrics.pulse().rate().empty()) pulse = metrics.pulse().rate().rbegin()->value();
            if (!metrics.breathing().rate().empty()) breathing = metrics.breathing().rate().rbegin()->value();

            const bool pulse_valid = (pulse >= 30.0f && pulse <= 200.0f);
            const bool breathing_valid = (breathing >= 2.0f && breathing <= 60.0f);
            
            if (pulse_valid || breathing_valid) {
                std::cout << "{\"type\": \"vitals\", \"pulse\": " << (pulse_valid ? pulse : 0.0f)
                          << ", \"breathing\": " << (breathing_valid ? breathing : 0.0f) << "}" << std::endl;
            }
            return absl::OkStatus();
        }
    );

    if (!status.ok()) { std::cerr << status.message() << "\n"; return 1; }
    if (auto s = container->Initialize(); !s.ok()) { std::cerr << "Init Failed: " << s.message() << "\n"; return 1; }
    if (auto s = container->Run(); !s.ok()) { std::cerr << "Run Failed: " << s.message() << "\n"; return 1; }

    return 0;
}
