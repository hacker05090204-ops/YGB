## Deferred - Requires C++ Toolchain

Fix 30: Single-pass DOM parser in edge/data_extractor.cpp lines 91-121
Fix 31: std::move for map return in edge/data_extractor.cpp lines 127-152

To apply: install g++ or Visual Studio Build Tools then run
cmake -B build -S edge && cmake --build build --config Release
These are performance improvements only, not correctness fixes.
The current code works correctly, just slower.
