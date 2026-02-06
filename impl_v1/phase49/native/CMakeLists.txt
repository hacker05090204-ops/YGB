cmake_minimum_required(VERSION 3.16)
project(phase49_browser_engine VERSION 1.0.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Compiler flags - Security hardening
if(MSVC)
    add_compile_options(/W4 /WX /GS /DYNAMICBASE /NXCOMPAT)
else()
    # Required security flags (Phase-49 enforcement)
    add_compile_options(
        -Wall -Wextra -Wpedantic -Werror -Wshadow
        -fstack-protector-strong      # Stack buffer overflow protection
        -D_FORTIFY_SOURCE=2           # Runtime buffer overflow checks
        -fPIE                         # Position Independent Executable
    )
    
    # Linker security flags
    add_link_options(
        -pie                          # PIE linking
        -Wl,-z,relro                  # Relocation Read-Only
        -Wl,-z,now                    # Immediate binding
        -Wl,-z,noexecstack            # Non-executable stack
    )
    
    # Debug/test builds: enable sanitizers
    if(CMAKE_BUILD_TYPE STREQUAL "Debug" OR ENABLE_SANITIZERS)
        add_compile_options(-fsanitize=address -fsanitize=undefined)
        add_link_options(-fsanitize=address -fsanitize=undefined)
        message(STATUS "AddressSanitizer ENABLED for security testing")
    endif()
endif()

# Browser engine library (shared for Python ctypes)
add_library(browser_engine SHARED
    browser_engine.cpp
)

target_include_directories(browser_engine PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}
)

# Set output name without 'lib' prefix on Windows
set_target_properties(browser_engine PROPERTIES
    OUTPUT_NAME "browser_engine"
    PREFIX ""
)

# Position independent code for shared library
set_target_properties(browser_engine PROPERTIES
    POSITION_INDEPENDENT_CODE ON
)

# Install rules
install(TARGETS browser_engine
    LIBRARY DESTINATION lib
    ARCHIVE DESTINATION lib
    RUNTIME DESTINATION bin
)

install(FILES browser_engine.h
    DESTINATION include/phase49
)

# Test executable (optional, for C++ testing)
option(BUILD_TESTS "Build C++ tests" OFF)
if(BUILD_TESTS)
    add_executable(test_browser_engine
        test_browser_engine.cpp
    )
    target_link_libraries(test_browser_engine PRIVATE browser_engine)
endif()
