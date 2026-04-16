cmake_minimum_required(VERSION 3.18)
project(YGB_Native LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

option(YGB_ENABLE_CUDA "Enable CUDA/NCCL integration when toolchains are available" ON)

add_library(ygb_native SHARED
    distributed/async_allreduce.cpp
    performance/gradient_accumulator.cpp
    security/data_truth_enforcer.cpp
)

target_include_directories(ygb_native PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})

if(YGB_ENABLE_CUDA)
    find_package(CUDAToolkit QUIET)
    find_path(NCCL_INCLUDE_DIR nccl.h)
    find_library(NCCL_LIBRARY nccl)

    if(CUDAToolkit_FOUND AND NCCL_INCLUDE_DIR AND NCCL_LIBRARY)
        target_include_directories(ygb_native PRIVATE ${CUDAToolkit_INCLUDE_DIRS} ${NCCL_INCLUDE_DIR})
        target_link_libraries(ygb_native PRIVATE CUDA::cudart ${NCCL_LIBRARY})
        target_compile_definitions(ygb_native PRIVATE YGB_ENABLE_NCCL=1)
        message(STATUS "Building ygb_native with CUDA/NCCL support")
    else()
        message(WARNING "CUDA/NCCL not found; ygb_native will build with fail-closed distributed stubs")
    endif()
endif()
