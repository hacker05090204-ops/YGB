/*
 * gpu_optimizer.cpp — GPU Performance Optimization Engine (Phase 5)
 *
 * Monitor: utilization, VRAM, temperature
 * Maintain 65-80% band
 * Dynamic batch scaling
 * Mixed precision FP16
 * Gradient checkpointing
 * TF32 where stable
 *
 * C API for Python bridge.
 */

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>

#ifdef __cplusplus
extern "C" {
#endif

/* ------------------------------------------------------------------ */
/*  TYPES                                                              */
/* ------------------------------------------------------------------ */

typedef struct {
  double utilization; /* 0.0 - 1.0 */
  double vram_used_mb;
  double vram_total_mb;
  double temperature_c;
  int batch_size;
  int num_workers;
  int fp16_enabled;
  int gradient_checkpoint;
  int tf32_enabled;
} GpuOptState;

typedef struct {
  int action; /* 0=none, 1=increase_batch, -1=decrease */
  int new_batch_size;
  int fp16_recommended;
  int checkpoint_recommended;
  int tf32_recommended;
  int throttled;
  double score; /* 0-1 optimization score */
} OptDecision;

/* ------------------------------------------------------------------ */
/*  GLOBALS                                                            */
/* ------------------------------------------------------------------ */

static GpuOptState g_state;
static int g_initialized = 0;

#define TARGET_LOW 0.65
#define TARGET_HIGH 0.80
#define TEMP_WARNING 80.0
#define TEMP_THROTTLE 85.0
#define MIN_BATCH 4
#define MAX_BATCH 256

/* ------------------------------------------------------------------ */
/*  PUBLIC API                                                         */
/* ------------------------------------------------------------------ */

int gpu_opt_init(int batch_size, double vram_total_mb) {
  memset(&g_state, 0, sizeof(g_state));
  g_state.batch_size = batch_size;
  g_state.num_workers = 2;
  g_state.vram_total_mb = vram_total_mb;
  g_state.fp16_enabled = 1; /* Default on */
  g_state.gradient_checkpoint = 0;
  g_state.tf32_enabled = 1;
  g_initialized = 1;
  return 0;
}

OptDecision gpu_opt_step(double utilization, double vram_used_mb,
                         double temperature_c) {
  OptDecision d;
  memset(&d, 0, sizeof(d));

  g_state.utilization = utilization;
  g_state.vram_used_mb = vram_used_mb;
  g_state.temperature_c = temperature_c;

  d.fp16_recommended = 1; /* Always recommend FP16 */
  d.tf32_recommended = 1;
  d.checkpoint_recommended =
      (vram_used_mb > g_state.vram_total_mb * 0.85) ? 1 : 0;
  d.throttled = 0;

  /* Thermal throttle */
  if (temperature_c >= TEMP_THROTTLE) {
    d.action = -1;
    d.new_batch_size = g_state.batch_size > MIN_BATCH
                           ? g_state.batch_size - g_state.batch_size / 4
                           : MIN_BATCH;
    d.throttled = 1;
    d.score = 0.3;
    g_state.batch_size = d.new_batch_size;
    return d;
  }

  /* Utilization control */
  if (utilization < TARGET_LOW) {
    /* Under-utilized → increase batch */
    int inc = g_state.batch_size / 4;
    if (inc < 1)
      inc = 1;
    d.action = 1;
    d.new_batch_size = g_state.batch_size + inc;
    if (d.new_batch_size > MAX_BATCH)
      d.new_batch_size = MAX_BATCH;
    d.score = 0.6;
  } else if (utilization > TARGET_HIGH) {
    /* Over-utilized → decrease batch */
    int dec = g_state.batch_size / 8;
    if (dec < 1)
      dec = 1;
    d.action = -1;
    d.new_batch_size = g_state.batch_size - dec;
    if (d.new_batch_size < MIN_BATCH)
      d.new_batch_size = MIN_BATCH;
    d.score = 0.7;
  } else {
    /* In target band */
    d.action = 0;
    d.new_batch_size = g_state.batch_size;
    d.score = 1.0;
  }

  /* VRAM pressure → enable gradient checkpointing */
  if (vram_used_mb > g_state.vram_total_mb * 0.90) {
    d.checkpoint_recommended = 1;
    g_state.gradient_checkpoint = 1;
  }

  g_state.batch_size = d.new_batch_size;
  return d;
}

void gpu_opt_get_state(GpuOptState *out) {
  if (out)
    *out = g_state;
}

double gpu_opt_get_utilization(void) { return g_state.utilization; }

int gpu_opt_get_batch_size(void) { return g_state.batch_size; }

#ifdef __cplusplus
}
#endif
