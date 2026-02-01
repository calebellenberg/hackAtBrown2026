cmake_minimum_required(VERSION 3.14)

cmake_policy(SET CMP0077 NEW)

project(HeadlessVitals)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# --- FIND PACKAGES ---
# SmartSpectra depends on PhysiologyEdge which bundles Abseil, Protobuf, glog, etc.
find_package(SmartSpectra REQUIRED)
find_package(OpenCV REQUIRED)
find_package(Threads REQUIRED)

# --- BUILD EXECUTABLE ---
add_executable(headless_vitals headless_vitals.cpp)

# --- LINKING ---
# SmartSpectra::Container transitively links Physiology::Edge which includes
# all bundled dependencies (Abseil, Protobuf, gRPC, glog, etc.)
target_link_libraries(headless_vitals
    PRIVATE
    SmartSpectra::Container
    ${OpenCV_LIBS}
    Threads::Threads
)
