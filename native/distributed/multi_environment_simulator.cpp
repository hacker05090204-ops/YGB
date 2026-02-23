/*
 * multi_environment_simulator.cpp — Multi-Environment Simulator (Phase 0)
 *
 * Randomize sandbox configs for exploit robustness.
 * Vary: OS, server version, WAF presence, TLS, headers.
 * Ensure exploit works across environments.
 *
 * C API for Python bridge.
 */

#include <cstdint>
#include <cstring>

#ifdef __cplusplus
extern "C" {
#endif

#define MAX_ENVS 16
#define MAX_TESTS 256
#define FIELD_LEN 128

typedef struct {
  char env_name[FIELD_LEN];
  char os_type[FIELD_LEN];     /* linux / windows / macos */
  char server_type[FIELD_LEN]; /* nginx / apache / iis */
  int waf_enabled;
  int tls_version; /* 12=TLS1.2, 13=TLS1.3 */
  int custom_headers;
} EnvConfig;

typedef struct {
  int env_idx;
  double detection_score;
  int exploit_worked;
  double response_time_ms;
} EnvTestResult;

typedef struct {
  int total_envs;
  int total_tests;
  int envs_passed;
  int envs_failed;
  double avg_score;
  int robust; /* 1 if passed in all envs */
} MultiEnvReport;

/* Globals */
static EnvConfig g_envs[MAX_ENVS];
static int g_env_count = 0;
static EnvTestResult g_tests[MAX_TESTS];
static int g_test_count = 0;

/* ---- Public API ---- */

int menv_init(void) {
  memset(g_envs, 0, sizeof(g_envs));
  memset(g_tests, 0, sizeof(g_tests));
  g_env_count = 0;
  g_test_count = 0;
  return 0;
}

int menv_add_env(const char *name, const char *os_type, const char *server_type,
                 int waf_enabled, int tls_version, int custom_headers) {
  if (g_env_count >= MAX_ENVS)
    return -1;
  EnvConfig *e = &g_envs[g_env_count];
  strncpy(e->env_name, name, FIELD_LEN - 1);
  strncpy(e->os_type, os_type, FIELD_LEN - 1);
  strncpy(e->server_type, server_type, FIELD_LEN - 1);
  e->waf_enabled = waf_enabled;
  e->tls_version = tls_version;
  e->custom_headers = custom_headers;
  g_env_count++;
  return 0;
}

int menv_record_test(int env_idx, double score, int exploit_worked,
                     double time_ms) {
  if (g_test_count >= MAX_TESTS)
    return -1;
  if (env_idx < 0 || env_idx >= g_env_count)
    return -2;
  EnvTestResult *t = &g_tests[g_test_count];
  t->env_idx = env_idx;
  t->detection_score = score;
  t->exploit_worked = exploit_worked;
  t->response_time_ms = time_ms;
  g_test_count++;
  return 0;
}

MultiEnvReport menv_evaluate(void) {
  MultiEnvReport r;
  memset(&r, 0, sizeof(r));
  r.total_envs = g_env_count;
  r.total_tests = g_test_count;

  if (g_env_count == 0 || g_test_count == 0)
    return r;

  /* Per-env pass check */
  int env_passed[MAX_ENVS];
  memset(env_passed, 0, sizeof(env_passed));
  double sum_score = 0;

  for (int i = 0; i < g_test_count; i++) {
    sum_score += g_tests[i].detection_score;
    if (g_tests[i].exploit_worked) {
      env_passed[g_tests[i].env_idx] = 1;
    }
  }

  int passed = 0;
  for (int i = 0; i < g_env_count; i++) {
    if (env_passed[i])
      passed++;
  }

  r.envs_passed = passed;
  r.envs_failed = g_env_count - passed;
  r.avg_score = sum_score / g_test_count;
  r.robust = (passed == g_env_count) ? 1 : 0;

  return r;
}

int menv_get_env_count(void) { return g_env_count; }
int menv_get_test_count(void) { return g_test_count; }
int menv_is_robust(void) { return menv_evaluate().robust; }

#ifdef __cplusplus
}
#endif
