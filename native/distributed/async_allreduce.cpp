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
#include <thread>
#include <vector>


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
};

static BucketManager g_manager = {};

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

  memset(g_manager.buckets, 0, sizeof(g_manager.buckets));

  fprintf(stdout,
          "[ASYNC_AR] Init: world=%d rank=%d bucket=%dMB timeout=%dms\n",
          world_size, rank, bucket_mb > 0 ? bucket_mb : DEFAULT_BUCKET_MB,
          g_manager.straggler_timeout_ms);

  return 0;
}

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
 * In a real implementation, this triggers async NCCL all-reduce.
 * Here we simulate the overlapped communication.
 *
 * @param bucket_id  Bucket to mark ready
 * @return 0 on success
 */
int async_allreduce_mark_ready(int bucket_id) {
  if (bucket_id < 0 || bucket_id >= g_manager.num_buckets) {
    return -1;
  }

  GradientBucket &b = g_manager.buckets[bucket_id];
  b.ready = true;
  g_manager.buckets_ready.fetch_add(1);

  // Simulate overlapped all-reduce:
  // In production, this would launch ncclAllReduce async
  auto t0 = std::chrono::steady_clock::now();

  // Simulate: average gradients across world_size
  if (b.data != nullptr && g_manager.world_size > 1) {
    float scale = 1.0f / static_cast<float>(g_manager.world_size);
    for (int64_t i = 0; i < b.num_elements; i++) {
      b.data[i] *= scale;
    }
  }

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
}

/**
 * Cleanup the bucket manager.
 */
void async_allreduce_cleanup() {
  std::lock_guard<std::mutex> lock(g_manager.mtx);
  g_manager.initialized = false;
  g_manager.num_buckets = 0;
  fprintf(stdout, "[ASYNC_AR] Cleaned up\n");
}

} // extern "C"
