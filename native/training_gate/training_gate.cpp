/**
 * training_gate.cpp — Final Training Start Gate
 *
 * Before MODE_A training begins, ALL conditions must pass:
 *   1. Device identity exists and is valid
 *   2. Device is registered in device_registry
 *   3. Device is paired (valid certificate)
 *   4. WireGuard mesh is active
 *   5. Cluster has quorum (>=1 AUTHORITY, >=1 STORAGE, >=1 WORKER)
 *   6. Governance is NOT frozen
 *   7. HMAC secret is configured
 *   8. Disk encryption verified (LUKS/BitLocker)
 *
 * If ANY gate fails → training DOES NOT START.
 * ALL gate results logged to reports/training_gate.json.
 *
 * NO override. NO bypass. NO partial start.
 */

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <ctime>

namespace training_gate {

// =========================================================================
// GATE RESULT
// =========================================================================

enum class GateResult : uint8_t {
  PASS = 0,
  FAIL_IDENTITY = 1,
  FAIL_REGISTRY = 2,
  FAIL_PAIRING = 3,
  FAIL_MESH = 4,
  FAIL_QUORUM = 5,
  FAIL_GOVERNANCE = 6,
  FAIL_HMAC = 7,
  FAIL_ENCRYPTION = 8,
};

static const char *gate_name(GateResult g) {
  switch (g) {
  case GateResult::PASS:
    return "PASS";
  case GateResult::FAIL_IDENTITY:
    return "FAIL_IDENTITY";
  case GateResult::FAIL_REGISTRY:
    return "FAIL_REGISTRY";
  case GateResult::FAIL_PAIRING:
    return "FAIL_PAIRING";
  case GateResult::FAIL_MESH:
    return "FAIL_MESH";
  case GateResult::FAIL_QUORUM:
    return "FAIL_QUORUM";
  case GateResult::FAIL_GOVERNANCE:
    return "FAIL_GOVERNANCE";
  case GateResult::FAIL_HMAC:
    return "FAIL_HMAC";
  case GateResult::FAIL_ENCRYPTION:
    return "FAIL_ENCRYPTION";
  default:
    return "UNKNOWN";
  }
}

// =========================================================================
// GATE INPUT — populated by orchestration layer
// =========================================================================

struct GateInput {
  bool identity_valid;
  bool registered;
  bool paired;
  bool mesh_active;
  bool quorum_met;
  bool governance_unlocked;
  bool hmac_configured;
  bool disk_encrypted;
};

// =========================================================================
// GATE CHECK
// =========================================================================

struct GateCheckResult {
  GateResult results[8];
  int pass_count;
  int fail_count;
  bool all_pass;
};

static constexpr char GATE_LOG_PATH[] = "reports/training_gate.json";

static GateCheckResult check_gates(const GateInput &input) {
  GateCheckResult out = {};
  out.pass_count = 0;
  out.fail_count = 0;
  out.all_pass = true;

  // Gate 1: Device identity
  out.results[0] =
      input.identity_valid ? GateResult::PASS : GateResult::FAIL_IDENTITY;
  // Gate 2: Registry
  out.results[1] =
      input.registered ? GateResult::PASS : GateResult::FAIL_REGISTRY;
  // Gate 3: Pairing
  out.results[2] = input.paired ? GateResult::PASS : GateResult::FAIL_PAIRING;
  // Gate 4: Mesh
  out.results[3] = input.mesh_active ? GateResult::PASS : GateResult::FAIL_MESH;
  // Gate 5: Quorum
  out.results[4] =
      input.quorum_met ? GateResult::PASS : GateResult::FAIL_QUORUM;
  // Gate 6: Governance
  out.results[5] = input.governance_unlocked ? GateResult::PASS
                                             : GateResult::FAIL_GOVERNANCE;
  // Gate 7: HMAC
  out.results[6] =
      input.hmac_configured ? GateResult::PASS : GateResult::FAIL_HMAC;
  // Gate 8: Encryption
  out.results[7] =
      input.disk_encrypted ? GateResult::PASS : GateResult::FAIL_ENCRYPTION;

  for (int i = 0; i < 8; ++i) {
    if (out.results[i] == GateResult::PASS) {
      out.pass_count++;
    } else {
      out.fail_count++;
      out.all_pass = false;
    }
  }

  return out;
}

// =========================================================================
// LOGGING
// =========================================================================

static void log_gate_result(const GateCheckResult &result) {
  FILE *f = std::fopen(GATE_LOG_PATH, "a");
  if (!f)
    return;

  uint64_t now = static_cast<uint64_t>(std::time(nullptr));
  std::fprintf(f,
               "{\"timestamp\": %llu, \"all_pass\": %s, "
               "\"pass_count\": %d, \"fail_count\": %d, "
               "\"gates\": [",
               static_cast<unsigned long long>(now),
               result.all_pass ? "true" : "false", result.pass_count,
               result.fail_count);

  for (int i = 0; i < 8; ++i) {
    std::fprintf(f, "\"%s\"%s", gate_name(result.results[i]),
                 i < 7 ? ", " : "");
  }
  std::fprintf(f, "]}\n");
  std::fclose(f);
}

// =========================================================================
// PUBLIC API
// =========================================================================

static bool can_start_training(const GateInput &input) {
  GateCheckResult result = check_gates(input);
  log_gate_result(result);
  return result.all_pass;
}

// =========================================================================
// SELF-TEST
// =========================================================================

#ifdef RUN_SELF_TEST
static int self_test() {
  int pass = 0, fail = 0;

  // Test 1: All gates pass
  GateInput full = {true, true, true, true, true, true, true, true};
  auto r1 = check_gates(full);
  if (r1.all_pass && r1.pass_count == 8) {
    ++pass;
  } else {
    ++fail;
  }

  // Test 2: Missing identity
  GateInput no_id = {false, true, true, true, true, true, true, true};
  auto r2 = check_gates(no_id);
  if (!r2.all_pass && r2.fail_count == 1) {
    ++pass;
  } else {
    ++fail;
  }
  if (r2.results[0] == GateResult::FAIL_IDENTITY) {
    ++pass;
  } else {
    ++fail;
  }

  // Test 3: Missing quorum
  GateInput no_quorum = {true, true, true, true, false, true, true, true};
  auto r3 = check_gates(no_quorum);
  if (!r3.all_pass) {
    ++pass;
  } else {
    ++fail;
  }
  if (r3.results[4] == GateResult::FAIL_QUORUM) {
    ++pass;
  } else {
    ++fail;
  }

  // Test 4: Governance frozen
  GateInput frozen = {true, true, true, true, true, false, true, true};
  auto r4 = check_gates(frozen);
  if (!r4.all_pass) {
    ++pass;
  } else {
    ++fail;
  }
  if (r4.results[5] == GateResult::FAIL_GOVERNANCE) {
    ++pass;
  } else {
    ++fail;
  }

  // Test 5: All gates fail
  GateInput none = {false, false, false, false, false, false, false, false};
  auto r5 = check_gates(none);
  if (!r5.all_pass && r5.fail_count == 8) {
    ++pass;
  } else {
    ++fail;
  }

  // Test 6: can_start_training returns correctly
  if (can_start_training(full)) {
    ++pass;
  } else {
    ++fail;
  }
  if (!can_start_training(no_id)) {
    ++pass;
  } else {
    ++fail;
  }

  std::printf("training_gate self-test: %d passed, %d failed\n", pass, fail);
  return fail == 0 ? 0 : 1;
}
#endif

} // namespace training_gate
