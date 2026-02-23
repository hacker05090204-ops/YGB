/*
 * performance_optimizer.cpp — Performance Optimization Engine (Phase 6)
 *
 * ██████████████████████████████████████████████████████████████████████
 * BOUNTY-READY — TRAINING PERFORMANCE OPTIMIZATION
 * ██████████████████████████████████████████████████████████████████████
 *
 * Performance-critical (C++):
 *   1. Dynamic batch scaler — adjust batch size based on throughput
 *   2. IO overlap tracker — pipeline data loading with training
 *   3. FP16/TF32 precision selector — select optimal precision
 *   4. Thermal throttle — reduce load on thermal limit
 *   5. GPU utilization target — maintain 65-80%
 *
 * Compile (Windows):
 *   g++ -shared -O2 -o performance_optimizer.dll performance_optimizer.cpp
 */

#ifdef _WIN32
#define PO_EXPORT __declspec(dllexport)
#else
#define PO_EXPORT __attribute__((visibility("default")))
#endif

#ifdef __cplusplus
extern "C" {
#endif

/* ================================================================== */
/*  CONSTANTS                                                         */
/* ================================================================== */

#define MIN_BATCH_SIZE 8
#define MAX_BATCH_SIZE 512
#define GPU_TARGET_LOW 65      /* Minimum GPU utilization % */
#define GPU_TARGET_HIGH 80     /* Maximum GPU utilization % */
#define THERMAL_LIMIT 85       /* Temperature °C to start throttling */
#define THERMAL_CRITICAL 95    /* Temperature °C for hard throttle */
#define IO_OVERLAP_TARGET 0.80 /* Target IO/compute overlap ratio */

/* ================================================================== */
/*  STATE                                                             */
/* ================================================================== */

typedef struct {
  /* Batch scaler */
  int current_batch_size;
  int min_batch;
  int max_batch;
  double throughput_samples_per_sec;

  /* IO overlap */
  double io_load_ms;
  double compute_ms;
  double overlap_ratio;

  /* Precision */
  int precision_mode; /* 0=FP32, 1=FP16, 2=TF32 */

  /* Thermal */
  int gpu_temp_c;
  int thermal_throttled;
  double throttle_factor; /* 1.0 = no throttle, 0.5 = halved */

  /* GPU utilization */
  int gpu_utilization;
  int in_target_range;
} PerformanceState;

static PerformanceState g_state = {
    .current_batch_size = 32,
    .min_batch = MIN_BATCH_SIZE,
    .max_batch = MAX_BATCH_SIZE,
    .precision_mode = 0,
    .throttle_factor = 1.0,
};

/* ================================================================== */
/*  DYNAMIC BATCH SCALER                                              */
/* ================================================================== */

/*
 * batch_scale — Adjust batch size based on GPU utilization + memory.
 *
 * gpu_util: Current GPU utilization %
 * memory_used_mb: Current GPU memory usage
 * memory_total_mb: Total GPU memory
 *
 * Returns: recommended batch size
 */
PO_EXPORT int batch_scale(int gpu_util, int memory_used_mb,
                          int memory_total_mb) {
  g_state.gpu_utilization = gpu_util;
  int bs = g_state.current_batch_size;

  double mem_ratio =
      (double)memory_used_mb / (memory_total_mb > 0 ? memory_total_mb : 1);

  /* Scale up if underutilized and memory available */
  if (gpu_util < GPU_TARGET_LOW && mem_ratio < 0.75) {
    bs = (int)(bs * 1.25);
  }
  /* Scale down if overutilized or memory pressure */
  else if (gpu_util > GPU_TARGET_HIGH || mem_ratio > 0.90) {
    bs = (int)(bs * 0.80);
  }

  /* Apply thermal throttle */
  bs = (int)(bs * g_state.throttle_factor);

  /* Clamp */
  if (bs < g_state.min_batch)
    bs = g_state.min_batch;
  if (bs > g_state.max_batch)
    bs = g_state.max_batch;

  /* Round to multiple of 8 for GPU efficiency */
  bs = (bs / 8) * 8;
  if (bs < g_state.min_batch)
    bs = g_state.min_batch;

  g_state.current_batch_size = bs;
  g_state.in_target_range =
      (gpu_util >= GPU_TARGET_LOW && gpu_util <= GPU_TARGET_HIGH);

  return bs;
}

/* ================================================================== */
/*  IO OVERLAP TRACKER                                                */
/* ================================================================== */

/*
 * io_update — Record IO and compute timings for overlap analysis.
 */
PO_EXPORT void io_update(double io_load_ms, double compute_ms) {
  g_state.io_load_ms = io_load_ms;
  g_state.compute_ms = compute_ms;

  double total = io_load_ms + compute_ms;
  if (total > 0) {
    /* Overlap = how much IO is hidden behind compute */
    double hidden_io = (io_load_ms < compute_ms) ? io_load_ms : compute_ms;
    g_state.overlap_ratio = hidden_io / total;
  } else {
    g_state.overlap_ratio = 0.0;
  }
}

/*
 * io_should_prefetch — Should we prefetch more data?
 * Returns: 1 if IO is the bottleneck, 0 if compute-bound
 */
PO_EXPORT int io_should_prefetch(void) {
  return (g_state.io_load_ms > g_state.compute_ms * 1.2) ? 1 : 0;
}

/* ================================================================== */
/*  PRECISION SELECTOR                                                */
/* ================================================================== */

/*
 * select_precision — Choose optimal precision based on hardware.
 *
 * has_fp16: GPU supports FP16
 * has_tf32: GPU supports TF32 (Ampere+)
 * accuracy_sensitive: 1 if training accuracy is priority
 *
 * Returns: 0=FP32, 1=FP16, 2=TF32
 */
PO_EXPORT int select_precision(int has_fp16, int has_tf32,
                               int accuracy_sensitive) {
  if (accuracy_sensitive) {
    /* Prefer TF32 if available (Ampere+), else FP32 */
    g_state.precision_mode = has_tf32 ? 2 : 0;
  } else {
    /* Prefer FP16 for speed, TF32 fallback, then FP32 */
    if (has_fp16)
      g_state.precision_mode = 1;
    else if (has_tf32)
      g_state.precision_mode = 2;
    else
      g_state.precision_mode = 0;
  }
  return g_state.precision_mode;
}

/* ================================================================== */
/*  THERMAL THROTTLE                                                  */
/* ================================================================== */

/*
 * thermal_update — Update GPU temperature and compute throttle factor.
 *
 * temp_c: Current GPU temperature in Celsius
 * Returns: throttle factor (1.0 = no throttle, <1.0 = throttled)
 */
PO_EXPORT double thermal_update(int temp_c) {
  g_state.gpu_temp_c = temp_c;

  if (temp_c >= THERMAL_CRITICAL) {
    g_state.throttle_factor = 0.25; /* Severe throttle */
    g_state.thermal_throttled = 1;
  } else if (temp_c >= THERMAL_LIMIT) {
    /* Linear throttle between 85-95°C */
    double t =
        (double)(temp_c - THERMAL_LIMIT) / (THERMAL_CRITICAL - THERMAL_LIMIT);
    g_state.throttle_factor = 1.0 - (0.75 * t); /* 1.0 → 0.25 */
    g_state.thermal_throttled = 1;
  } else {
    g_state.throttle_factor = 1.0;
    g_state.thermal_throttled = 0;
  }

  return g_state.throttle_factor;
}

/* ================================================================== */
/*  THROUGHPUT                                                        */
/* ================================================================== */

/*
 * update_throughput — Record training throughput.
 */
PO_EXPORT void update_throughput(double samples_per_sec) {
  g_state.throughput_samples_per_sec = samples_per_sec;
}

/* ================================================================== */
/*  STATUS QUERIES                                                    */
/* ================================================================== */

PO_EXPORT int po_batch_size(void) { return g_state.current_batch_size; }
PO_EXPORT int po_precision(void) { return g_state.precision_mode; }
PO_EXPORT int po_gpu_util(void) { return g_state.gpu_utilization; }
PO_EXPORT int po_gpu_temp(void) { return g_state.gpu_temp_c; }
PO_EXPORT int po_is_throttled(void) { return g_state.thermal_throttled; }
PO_EXPORT int po_in_target(void) { return g_state.in_target_range; }

PO_EXPORT double po_throttle_factor(void) { return g_state.throttle_factor; }
PO_EXPORT double po_throughput(void) {
  return g_state.throughput_samples_per_sec;
}
PO_EXPORT double po_overlap_ratio(void) { return g_state.overlap_ratio; }

#ifdef __cplusplus
}
#endif
