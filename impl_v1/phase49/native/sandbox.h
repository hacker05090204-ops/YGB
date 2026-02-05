// sandbox.h
// Phase-49: Native Process Sandbox Hardening
//
// STRICT RULES:
// - NO feature changes
// - NO governance changes
// - HARDENING ONLY
// - Zero blast radius on compromise

#ifndef PHASE49_SANDBOX_H
#define PHASE49_SANDBOX_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

// Sandbox configuration
typedef struct {
  uint32_t runner_uid;       // ygb-runner UID
  uint32_t runner_gid;       // ygb-runner GID
  const char *chroot_path;   // Jail root path
  const char *write_dirs[8]; // Writable directories (NULL-terminated)
  uint64_t max_memory;       // RLIMIT_AS in bytes
  uint32_t max_files;        // RLIMIT_NOFILE
  uint32_t max_procs;        // RLIMIT_NPROC
  bool allow_unix_socket;    // AF_UNIX for DevTools
  bool allow_core_dump;      // RLIMIT_CORE
} SandboxConfig;

// Sandbox result
typedef struct {
  bool success;
  int error_code;
  const char *error_message;
} SandboxResult;

// ============================================================
// SANDBOX API
// ============================================================

// Initialize sandbox with configuration
SandboxResult sandbox_init(const SandboxConfig *config);

// Drop privileges to ygb-runner user
// MUST be called immediately after fork
SandboxResult sandbox_drop_privileges(void);

// Apply seccomp-BPF filter
// Blocks dangerous syscalls post-launch
SandboxResult sandbox_apply_seccomp(void);

// Apply filesystem jail
// chroot + chdir to working directory
SandboxResult sandbox_apply_fs_jail(void);

// Set resource limits
// RLIMIT_NOFILE, RLIMIT_NPROC, RLIMIT_AS, RLIMIT_CORE
SandboxResult sandbox_set_limits(void);

// Full sandbox initialization (calls all above in order)
SandboxResult sandbox_enter(const SandboxConfig *config);

// Verify sandbox is active
// Returns true if all restrictions are enforced
bool sandbox_verify(void);

// Get current sandbox status for logging
const char *sandbox_get_status(void);

// ============================================================
// DEFAULT CONFIGURATION
// ============================================================

// Get default configuration for YGB native engines
SandboxConfig sandbox_get_default_config(void);

#ifdef __cplusplus
}
#endif

#endif // PHASE49_SANDBOX_H
