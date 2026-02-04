# Makefile for Phase-49 Native Engines
# Build C++ engines as shared libraries for Python ctypes

CXX = g++
CXXFLAGS = -std=c++17 -fPIC -Wall -Wextra -O2
LDFLAGS = -shared

# Detect OS
UNAME_S := $(shell uname -s)
ifeq ($(UNAME_S),Linux)
    SHARED_EXT = .so
    LDFLAGS += -lpthread
endif
ifeq ($(UNAME_S),Darwin)
    SHARED_EXT = .dylib
endif

# Directories
SRC_DIR = .
BUILD_DIR = build
LIB_DIR = lib

# Source files
SOURCES = browser_engine.cpp \
          screenshot_engine.cpp \
          video_recorder.cpp \
          dom_diff_engine.cpp \
          network_capture.cpp \
          scope_adapter.cpp \
          rate_limiter.cpp \
          auth_boundary.cpp \
          asset_discovery.cpp

# Object files
OBJECTS = $(SOURCES:%.cpp=$(BUILD_DIR)/%.o)

# Library targets
LIBS = $(LIB_DIR)/libnative_engines$(SHARED_EXT)

.PHONY: all clean test

all: dirs $(LIBS)

dirs:
	@mkdir -p $(BUILD_DIR)
	@mkdir -p $(LIB_DIR)

$(BUILD_DIR)/%.o: $(SRC_DIR)/%.cpp
	$(CXX) $(CXXFLAGS) -c $< -o $@

$(LIB_DIR)/libnative_engines$(SHARED_EXT): $(OBJECTS)
	$(CXX) $(LDFLAGS) $^ -o $@

clean:
	rm -rf $(BUILD_DIR) $(LIB_DIR)

# Individual library builds (for debugging)
browser: dirs $(BUILD_DIR)/browser_engine.o
	$(CXX) $(LDFLAGS) $(BUILD_DIR)/browser_engine.o -o $(LIB_DIR)/libbrowser$(SHARED_EXT)

screenshot: dirs $(BUILD_DIR)/screenshot_engine.o
	$(CXX) $(LDFLAGS) $(BUILD_DIR)/screenshot_engine.o -o $(LIB_DIR)/libscreenshot$(SHARED_EXT)

# Test target
test:
	@echo "Testing native engine compilation..."
	@$(MAKE) all
	@echo "Build successful!"
	@ls -la $(LIB_DIR)/
