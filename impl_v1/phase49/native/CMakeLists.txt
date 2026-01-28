cmake_minimum_required(VERSION 3.16)
project(phase49_browser_engine VERSION 1.0.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Compiler flags
if(MSVC)
    add_compile_options(/W4 /WX)
else()
    add_compile_options(-Wall -Wextra -Wpedantic -Werror)
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
