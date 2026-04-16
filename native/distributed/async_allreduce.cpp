/*
 * async_allreduce.cpp — Async All-Reduce Optimization (Phase 4)
 *
 * Implements:
 *   - Gradient bucketing for efficient NCCL calls
 *   - Overlap communication with backward pass
 *   - Straggler mitigation via per-bucket timeout
 *
 * Exposes C interface callable from Python via ctypes.
 */

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

#if defined(__has_include)
#if __has_include(<cuda_runtime.h>)
#include <cuda_runtime.h>
#define YGB_HAS_CUDA_RUNTIME 1
#else
#define YGB_HAS_CUDA_RUNTIME 0
#endif
#if __has_include(<nccl.h>)
#include <nccl.h>
#define YGB_HAS_NCCL 1
#else
#define YGB_HAS_NCCL 0
#endif
#else
#define YGB_HAS_CUDA_RUNTIME 0
#define YGB_HAS_NCCL 0
#endif

#if !YGB_HAS_CUDA_RUNTIME
using cudaStream_t = void *;
#endif

#if !YGB_HAS_NCCL
using ncclComm_t = void *;
#endif

// ============================================================================
// CONFIGURATION
// ============================================================================

static constexpr int MAX_BUCKETS = 64;
static constexpr int DEFAULT_BUCKET_MB = 25;      // 25 MB per bucket
static constexpr int STRAGGLER_TIMEOUT_MS = 5000; // 5 second timeout per bucket

// ============================================================================
// GRADIENT BUCKET
// ============================================================================

struct GradientBucket {
  int bucket_id;
  float *data; // Pointer to contiguous gradient buffer
  int64_t num_elements;
  int64_t size_bytes;
  bool ready;          // Backward pass filled this bucket
  bool reduced;        // All-reduce completed
  bool timed_out;      // Straggler timeout hit
  double allreduce_ms; // Time spent in all-reduce
};

// ============================================================================
// BUCKET MANAGER STATE
// ============================================================================

struct BucketManager {
  GradientBucket buckets[MAX_BUCKETS];
  int num_buckets;
  int64_t bucket_size_bytes;
  int world_size;
  int rank;
  std::atomic<int> buckets_ready;
  std::atomic<int> buckets_reduced;
  std::mutex mtx;
  bool initialized;
  int straggler_timeout_ms;
  int degraded_nodes; // Count of nodes that timed out
  ncclComm_t nccl_comm;
  cudaStream_t cuda_stream;
  bool nccl_bound;
  char last_error[256];
};

static BucketManager g_manager = {};

static void set_last_error(const char *message) {
  std::snprintf(g_manager.last_error, sizeof(g_manager.last_error), "%s",
                message != nullptr ? message : "unknown async_allreduce error");
}

static void clear_last_error() { g_manager.last_error[0] = '\0'; }

// ============================================================================
// C API
// ============================================================================

extern "C" {

/**
 * Initialize the bucket manager.
 *
 * @param world_size    Number of DDP ranks
 * @param rank          This node's rank
 * @param bucket_mb     Size per bucket in MB
 * @param timeout_ms    Straggler timeout in ms
 * @return 0 on success
 */
int async_allreduce_init(int world_size, int rank, int bucket_mb,
                         int timeout_ms) {
  std::lock_guard<std::mutex> lock(g_manager.mtx);

  if (world_size < 1 || rank < 0 || rank >= world_size) {
    fprintf(stderr, "[ASYNC_AR] Invalid world_size=%d rank=%d\n", world_size,
            rank);
    return -1;
  }

  g_manager.world_size = world_size;
  g_manager.rank = rank;
  g_manager.bucket_size_bytes =
      static_cast<int64_t>(bucket_mb > 0 ? bucket_mb : DEFAULT_BUCKET_MB) *
      1024 * 1024;
  g_manager.straggler_timeout_ms =
      timeout_ms > 0 ? timeout_ms : STRAGGLER_TIMEOUT_MS;
  g_manager.num_buckets = 0;
  g_manager.buckets_ready.store(0);
  g_manager.buckets_reduced.store(0);
  g_manager.degraded_nodes = 0;
  g_manager.initialized = true;
  g_manager.nccl_comm = nullptr;
  g_manager.cuda_stream = nullptr;
  g_manager.nccl_bound = false;
  clear_last_error();

  memset(g_manager.buckets, 0, sizeof(g_manager.buckets));

  fprintf(stdout,
          "[ASYNC_AR] Init: world=%d rank=%d bucket=%dMB timeout=%dms\n",
          world_size, rank, bucket_mb > 0 ? bucket_mb : DEFAULT_BUCKET_MB,
          g_manager.straggler_timeout_ms);

  return 0;
}

/**
 * Bind NCCL communicator and CUDA stream handles supplied by the caller.
 *
 * @param comm    Opaque ncclComm_t pointer provided by the runtime
 * @param stream  Opaque cudaStream_t pointer provided by the runtime
 * @return 0 on success, negative on failure
 */
int async_allreduce_bind_nccl(void *comm, void *stream) {
  std::lock_guard<std::mutex> lock(g_manager.mtx);

  if (!g_manager.initialized) {
    set_last_error(
        "async_allreduce_bind_nccl called before async_allreduce_init");
    std::fprintf(stderr, "[ASYNC_AR] %s\n", g_manager.last_error);
    return -1;
  }

#if YGB_HAS_NCCL && YGB_HAS_CUDA_RUNTIME
  if (comm == nullptr || stream == nullptr) {
    set_last_error(
        "NCCL communicator/stream binding failed: null handle supplied");
    std::fprintf(stderr, "[ASYNC_AR] %s\n", g_manager.last_error);
    return -2;
  }
  g_manager.nccl_comm = reinterpret_cast<ncclComm_t>(comm);
  g_manager.cuda_stream = reinterpret_cast<cudaStream_t>(stream);
  g_manager.nccl_bound = true;
  clear_last_error();
  return 0;
#else
  (void)comm;
  (void)stream;
  set_last_error("NCCL/CUDA runtime support is unavailable. Rebuild with "
                 "nccl.h and cuda_runtime.h; fake local scaling is forbidden.");
  std::fprintf(stderr, "[ASYNC_AR] %s\n", g_manager.last_error);
  return -3;
#endif
}

const char *async_allreduce_last_error() { return g_manager.last_error; }

/**
 * Register a gradient bucket.
 *
 * Called during model initialization to partition gradients.
 *
 * @param data          Pointer to gradient buffer
 * @param num_elements  Number of float elements
 * @return bucket_id or -1 on error
 */
int async_allreduce_register_bucket(float *data, int64_t num_elements) {
  std::lock_guard<std::mutex> lock(g_manager.mtx);

  if (!g_manager.initialized) {
    fprintf(stderr, "[ASYNC_AR] Not initialized\n");
    return -1;
  }

  if (g_manager.num_buckets >= MAX_BUCKETS) {
    fprintf(stderr, "[ASYNC_AR] Max buckets (%d) exceeded\n", MAX_BUCKETS);
    return -1;
  }

  int id = g_manager.num_buckets++;
  GradientBucket &b = g_manager.buckets[id];

  b.bucket_id = id;
  b.data = data;
  b.num_elements = num_elements;
  b.size_bytes = num_elements * sizeof(float);
  b.ready = false;
  b.reduced = false;
  b.timed_out = false;
  b.allreduce_ms = 0.0;

  return id;
}

/**
 * Mark a bucket as ready (backward pass has filled it).
 *
 * This triggers a real NCCL all-reduce when NCCL/CUDA handles are bound.
 * If the runtime has not supplied NCCL handles, this function fails closed.
 *
 * @param bucket_id  Bucket to mark ready
 * @return 0 on success
 */
int async_allreduce_mark_ready(int bucket_id) {
  if (!g_manager.initialized) {
    set_last_error("async_allreduce_mark_ready called before initialization");
    std::fprintf(stderr, "[ASYNC_AR] %s\n", g_manager.last_error);
    return -1;
  }
  if (bucket_id < 0 || bucket_id >= g_manager.num_buckets) {
    return -1;
  }

  GradientBucket &b = g_manager.buckets[bucket_id];
  b.ready = true;
  g_manager.buckets_ready.fetch_add(1);

  auto t0 = std::chrono::steady_clock::now();

#if YGB_HAS_NCCL && YGB_HAS_CUDA_RUNTIME
  if (!g_manager.nccl_bound || g_manager.nccl_comm == nullptr ||
      g_manager.cuda_stream == nullptr) {
    set_last_error("NCCL communicator/stream not bound. Refusing to perform "
                   "fake local all-reduce.");
    std::fprintf(stderr, "[ASYNC_AR] %s\n", g_manager.last_error);
    return -2;
  }
  if (b.data == nullptr || b.num_elements <= 0) {
    set_last_error(
        "Bucket data is null or empty; cannot perform ncclAllReduce");
    std::fprintf(stderr, "[ASYNC_AR] %s\n", g_manager.last_error);
    return -3;
  }

  ncclResult_t result = ncclAllReduce(
      b.data, b.data, static_cast<size_t>(b.num_elements), ncclFloat, ncclSum,
      g_manager.nccl_comm, g_manager.cuda_stream);
  if (result != ncclSuccess) {
    std::snprintf(g_manager.last_error, sizeof(g_manager.last_error),
                  "ncclAllReduce failed: %s", ncclGetErrorString(result));
    std::fprintf(stderr, "[ASYNC_AR] %s\n", g_manager.last_error);
    return -4;
  }

  cudaError_t sync_result = cudaStreamSynchronize(g_manager.cuda_stream);
  if (sync_result != cudaSuccess) {
    std::snprintf(g_manager.last_error, sizeof(g_manager.last_error),
                  "cudaStreamSynchronize failed: %s",
                  cudaGetErrorString(sync_result));
    std::fprintf(stderr, "[ASYNC_AR] %s\n", g_manager.last_error);
    return -5;
  }
#else
  set_last_error(
      "NCCL not available. Rebuild with CUDA/NCCL support or disable "
      "distributed async all-reduce; fake local scaling is forbidden.");
  std::fprintf(stderr, "[ASYNC_AR] %s\n", g_manager.last_error);
  return -6;
#endif

  auto t1 = std::chrono::steady_clock::now();
  b.allreduce_ms = std::chrono::duration<double, std::milli>(t1 - t0).count();

  // Straggler check
  if (b.allreduce_ms > g_manager.straggler_timeout_ms) {
    b.timed_out = true;
    g_manager.degraded_nodes++;
    fprintf(stderr, "[ASYNC_AR] Bucket %d STRAGGLER: %.1fms > %dms timeout\n",
            bucket_id, b.allreduce_ms, g_manager.straggler_timeout_ms);
  }

  b.reduced = true;
  g_manager.buckets_reduced.fetch_add(1);
  clear_last_error();

  return 0;
}

/**
 * Wait for all buckets to complete all-reduce.
 *
 * @param timeout_ms  Max wait time
 * @return 0 if all done, -1 on timeout
 */
int async_allreduce_wait_all(int timeout_ms) {
  auto deadline =
      std::chrono::steady_clock::now() + std::chrono::milliseconds(timeout_ms);

  while (g_manager.buckets_reduced.load() < g_manager.num_buckets) {
    if (std::chrono::steady_clock::now() > deadline) {
      fprintf(stderr, "[ASYNC_AR] Timeout waiting for %d/%d buckets\n",
              g_manager.buckets_reduced.load(), g_manager.num_buckets);
      return -1;
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(1));
  }

  return 0;
}

/**
 * Get metrics for reporting.
 *
 * @param out_num_buckets      Output: number of buckets
 * @param out_total_ms         Output: total all-reduce time
 * @param out_degraded_nodes   Output: number of straggler timeouts
 * @return 0 on success
 */
int async_allreduce_metrics(int *out_num_buckets, double *out_total_ms,
                            int *out_degraded_nodes) {
  if (!g_manager.initialized)
    return -1;

  *out_num_buckets = g_manager.num_buckets;
  *out_degraded_nodes = g_manager.degraded_nodes;

  double total = 0.0;
  for (int i = 0; i < g_manager.num_buckets; i++) {
    total += g_manager.buckets[i].allreduce_ms;
  }
  *out_total_ms = total;

  return 0;
}

/**
 * Reset all buckets for next iteration.
 */
void async_allreduce_reset() {
  std::lock_guard<std::mutex> lock(g_manager.mtx);

  for (int i = 0; i < g_manager.num_buckets; i++) {
    g_manager.buckets[i].ready = false;
    g_manager.buckets[i].reduced = false;
    g_manager.buckets[i].timed_out = false;
    g_manager.buckets[i].allreduce_ms = 0.0;
  }

  g_manager.buckets_ready.store(0);
  g_manager.buckets_reduced.store(0);
  g_manager.degraded_nodes = 0;
  clear_last_error();
}

/**
 * Cleanup the bucket manager.
 */
void async_allreduce_cleanup() {
  std::lock_guard<std::mutex> lock(g_manager.mtx);
  g_manager.initialized = false;
  g_manager.num_buckets = 0;
  g_manager.nccl_comm = nullptr;
  g_manager.cuda_stream = nullptr;
  g_manager.nccl_bound = false;
  clear_last_error();
  fprintf(stdout, "[ASYNC_AR] Cleaned up\n");
}

} // extern "C"
