#!/usr/bin/env bash
# Build headless_vitals (C++) in WSL/Linux.
# Prerequisites: SmartSpectra SDK and OpenCV installed (e.g. Presage PPA + libopencv-dev).

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

mkdir -p build
cd build
cmake ..
make -j"$(nproc 2>/dev/null || echo 2)"

echo ""
echo "Built: $SCRIPT_DIR/build/headless_vitals"
echo "Run broker.py from $SCRIPT_DIR; it will use ./build/headless_vitals"
