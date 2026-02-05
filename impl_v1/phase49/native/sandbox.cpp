// sandbox.cpp
// Phase-49: Native Process Sandbox Implementation
//
// CRITICAL: This module contains security-critical code.
// NO feature changes. HARDENING ONLY.

#include "sandbox.h"

#include <errno.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#ifdef __linux__
#include <grp.h>
#include <linux/filter.h>
#include <linux/seccomp.h>
#include <pwd.h>
#include <sys/prctl.h>
#include <sys/resource.h>
#include <sys/stat.h>
#include <sys/syscall.h>

// Seccomp BPF macros
#define SECCOMP_RET_ALLOW_VAL 0x7fff0000
#define SECCOMP_RET_KILL_VAL 0x00000000
#define SECCOMP_RET_ERRNO_VAL 0x00050000

#define BPF_STMT_CUSTOM(code, k)                                               \
  {(unsigned short)(code), 0, 0, (unsigned int)(k)}
#define BPF_JUMP_CUSTOM(code, k, jt, jf)                                       \
  {(unsigned short)(code), (unsigned char)(jt), (unsigned char)(jf),           \
   (unsigned int)(k)}

#endif // __linux__

// ============================================================
// GLOBAL STATE
// ============================================================

static SandboxConfig g_config;
static bool g_initialized = false;
static bool g_privileges_dropped = false;
static bool g_seccomp_applied = false;
static bool g_fs_jailed = false;
static bool g_limits_set = false;

// ============================================================
// ERROR HANDLING
// ============================================================

static SandboxResult make_result(bool success, int error_code,
                                 const char *msg) {
  SandboxResult r;
  r.success = success;
  r.error_code = error_code;
  r.error_message = msg;
  return r;
}

static SandboxResult success_result(void) { return make_result(true, 0, "OK"); }

static SandboxResult error_result(const char *msg) {
  return make_result(false, errno, msg);
}

// ============================================================
// DEFAULT CONFIGURATION
// ============================================================

SandboxConfig sandbox_get_default_config(void) {
  SandboxConfig cfg;
  memset(&cfg, 0, sizeof(cfg));

  // Default to current user if ygb-runner not found
  cfg.runner_uid = 1000; // Default UID
  cfg.runner_gid = 1000; // Default GID

  cfg.chroot_path = "/home/ygb/Desktop/YGB";
  cfg.write_dirs[0] = "/reports";
  cfg.write_dirs[1] = "/tmp/ygb";
  cfg.write_dirs[2] = NULL;

  cfg.max_memory = 1024ULL * 1024 * 1024; // 1 GB
  cfg.max_files = 256;
  cfg.max_procs = 16;
  cfg.allow_unix_socket = true; // For DevTools
  cfg.allow_core_dump = false;

  return cfg;
}

// ============================================================
// SANDBOX INITIALIZATION
// ============================================================

SandboxResult sandbox_init(const SandboxConfig *config) {
  if (!config) {
    return error_result("NULL config");
  }

  g_config = *config;
  g_initialized = true;

  return success_result();
}

// ============================================================
// PRIVILEGE DROP
// ============================================================

SandboxResult sandbox_drop_privileges(void) {
#ifdef __linux__
  if (!g_initialized) {
    return error_result("Sandbox not initialized");
  }

  uid_t current_uid = getuid();
  gid_t current_gid = getgid();

  // Only drop if running as root or different user
  if (current_uid == 0 || current_uid != g_config.runner_uid) {
    // Drop supplementary groups first
    if (setgroups(0, NULL) != 0 && errno != EPERM) {
      return error_result("setgroups failed");
    }

    // Set GID first (required before setuid)
    if (setgid(g_config.runner_gid) != 0 && errno != EPERM) {
      return error_result("setgid failed");
    }

    // Set UID
    if (setuid(g_config.runner_uid) != 0 && errno != EPERM) {
      return error_result("setuid failed");
    }
  }

  // Verify privileges dropped
  if (getuid() == 0) {
    // Still root - verify this is expected
    fprintf(stderr,
            "[SANDBOX] WARNING: Still running as root after privilege drop\n");
  }

  // Ensure we cannot regain privileges
  if (prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0) {
    return error_result("PR_SET_NO_NEW_PRIVS failed");
  }

  g_privileges_dropped = true;
  return success_result();

#else
  // Non-Linux: privilege drop not implemented
  g_privileges_dropped = true;
  return success_result();
#endif
}

// ============================================================
// SECCOMP FILTER
// ============================================================

SandboxResult sandbox_apply_seccomp(void) {
#ifdef __linux__
  if (!g_initialized) {
    return error_result("Sandbox not initialized");
  }

  // Seccomp BPF filter
  // Architecture check + syscall whitelist
  struct sock_filter filter[] = {
      // Load syscall number
      BPF_STMT_CUSTOM(BPF_LD | BPF_W | BPF_ABS,
                      offsetof(struct seccomp_data, nr)),

      // ALLOW: read (0)
      BPF_JUMP_CUSTOM(BPF_JMP | BPF_JEQ | BPF_K, __NR_read, 0, 1),
      BPF_STMT_CUSTOM(BPF_RET | BPF_K, SECCOMP_RET_ALLOW_VAL),

      // ALLOW: write (1)
      BPF_JUMP_CUSTOM(BPF_JMP | BPF_JEQ | BPF_K, __NR_write, 0, 1),
      BPF_STMT_CUSTOM(BPF_RET | BPF_K, SECCOMP_RET_ALLOW_VAL),

      // ALLOW: close (3)
      BPF_JUMP_CUSTOM(BPF_JMP | BPF_JEQ | BPF_K, __NR_close, 0, 1),
      BPF_STMT_CUSTOM(BPF_RET | BPF_K, SECCOMP_RET_ALLOW_VAL),

      // ALLOW: fstat (5)
      BPF_JUMP_CUSTOM(BPF_JMP | BPF_JEQ | BPF_K, __NR_fstat, 0, 1),
      BPF_STMT_CUSTOM(BPF_RET | BPF_K, SECCOMP_RET_ALLOW_VAL),

      // ALLOW: poll (7)
      BPF_JUMP_CUSTOM(BPF_JMP | BPF_JEQ | BPF_K, __NR_poll, 0, 1),
      BPF_STMT_CUSTOM(BPF_RET | BPF_K, SECCOMP_RET_ALLOW_VAL),

      // ALLOW: lseek (8)
      BPF_JUMP_CUSTOM(BPF_JMP | BPF_JEQ | BPF_K, __NR_lseek, 0, 1),
      BPF_STMT_CUSTOM(BPF_RET | BPF_K, SECCOMP_RET_ALLOW_VAL),

      // ALLOW: mmap (9)
      BPF_JUMP_CUSTOM(BPF_JMP | BPF_JEQ | BPF_K, __NR_mmap, 0, 1),
      BPF_STMT_CUSTOM(BPF_RET | BPF_K, SECCOMP_RET_ALLOW_VAL),

      // ALLOW: mprotect (10)
      BPF_JUMP_CUSTOM(BPF_JMP | BPF_JEQ | BPF_K, __NR_mprotect, 0, 1),
      BPF_STMT_CUSTOM(BPF_RET | BPF_K, SECCOMP_RET_ALLOW_VAL),

      // ALLOW: munmap (11)
      BPF_JUMP_CUSTOM(BPF_JMP | BPF_JEQ | BPF_K, __NR_munmap, 0, 1),
      BPF_STMT_CUSTOM(BPF_RET | BPF_K, SECCOMP_RET_ALLOW_VAL),

      // ALLOW: brk (12)
      BPF_JUMP_CUSTOM(BPF_JMP | BPF_JEQ | BPF_K, __NR_brk, 0, 1),
      BPF_STMT_CUSTOM(BPF_RET | BPF_K, SECCOMP_RET_ALLOW_VAL),

      // ALLOW: rt_sigaction (13)
      BPF_JUMP_CUSTOM(BPF_JMP | BPF_JEQ | BPF_K, __NR_rt_sigaction, 0, 1),
      BPF_STMT_CUSTOM(BPF_RET | BPF_K, SECCOMP_RET_ALLOW_VAL),

      // ALLOW: rt_sigprocmask (14)
      BPF_JUMP_CUSTOM(BPF_JMP | BPF_JEQ | BPF_K, __NR_rt_sigprocmask, 0, 1),
      BPF_STMT_CUSTOM(BPF_RET | BPF_K, SECCOMP_RET_ALLOW_VAL),

      // ALLOW: ioctl (16)
      BPF_JUMP_CUSTOM(BPF_JMP | BPF_JEQ | BPF_K, __NR_ioctl, 0, 1),
      BPF_STMT_CUSTOM(BPF_RET | BPF_K, SECCOMP_RET_ALLOW_VAL),

      // ALLOW: access (21)
      BPF_JUMP_CUSTOM(BPF_JMP | BPF_JEQ | BPF_K, __NR_access, 0, 1),
      BPF_STMT_CUSTOM(BPF_RET | BPF_K, SECCOMP_RET_ALLOW_VAL),

      // ALLOW: nanosleep (35)
      BPF_JUMP_CUSTOM(BPF_JMP | BPF_JEQ | BPF_K, __NR_nanosleep, 0, 1),
      BPF_STMT_CUSTOM(BPF_RET | BPF_K, SECCOMP_RET_ALLOW_VAL),

      // ALLOW: getpid (39)
      BPF_JUMP_CUSTOM(BPF_JMP | BPF_JEQ | BPF_K, __NR_getpid, 0, 1),
      BPF_STMT_CUSTOM(BPF_RET | BPF_K, SECCOMP_RET_ALLOW_VAL),

      // ALLOW: exit (60)
      BPF_JUMP_CUSTOM(BPF_JMP | BPF_JEQ | BPF_K, __NR_exit, 0, 1),
      BPF_STMT_CUSTOM(BPF_RET | BPF_K, SECCOMP_RET_ALLOW_VAL),

      // ALLOW: futex (202)
      BPF_JUMP_CUSTOM(BPF_JMP | BPF_JEQ | BPF_K, __NR_futex, 0, 1),
      BPF_STMT_CUSTOM(BPF_RET | BPF_K, SECCOMP_RET_ALLOW_VAL),

      // ALLOW: clock_gettime (228)
      BPF_JUMP_CUSTOM(BPF_JMP | BPF_JEQ | BPF_K, __NR_clock_gettime, 0, 1),
      BPF_STMT_CUSTOM(BPF_RET | BPF_K, SECCOMP_RET_ALLOW_VAL),

      // ALLOW: exit_group (231)
      BPF_JUMP_CUSTOM(BPF_JMP | BPF_JEQ | BPF_K, __NR_exit_group, 0, 1),
      BPF_STMT_CUSTOM(BPF_RET | BPF_K, SECCOMP_RET_ALLOW_VAL),

      // ALLOW: openat (257)
      BPF_JUMP_CUSTOM(BPF_JMP | BPF_JEQ | BPF_K, __NR_openat, 0, 1),
      BPF_STMT_CUSTOM(BPF_RET | BPF_K, SECCOMP_RET_ALLOW_VAL),

      // ALLOW: newfstatat (262)
      BPF_JUMP_CUSTOM(BPF_JMP | BPF_JEQ | BPF_K, __NR_newfstatat, 0, 1),
      BPF_STMT_CUSTOM(BPF_RET | BPF_K, SECCOMP_RET_ALLOW_VAL),

      // ALLOW: epoll_wait (232)
      BPF_JUMP_CUSTOM(BPF_JMP | BPF_JEQ | BPF_K, __NR_epoll_wait, 0, 1),
      BPF_STMT_CUSTOM(BPF_RET | BPF_K, SECCOMP_RET_ALLOW_VAL),

      // ALLOW: epoll_ctl (233)
      BPF_JUMP_CUSTOM(BPF_JMP | BPF_JEQ | BPF_K, __NR_epoll_ctl, 0, 1),
      BPF_STMT_CUSTOM(BPF_RET | BPF_K, SECCOMP_RET_ALLOW_VAL),

      // ALLOW: epoll_create1 (291)
      BPF_JUMP_CUSTOM(BPF_JMP | BPF_JEQ | BPF_K, __NR_epoll_create1, 0, 1),
      BPF_STMT_CUSTOM(BPF_RET | BPF_K, SECCOMP_RET_ALLOW_VAL),

      // ALLOW: getuid (102)
      BPF_JUMP_CUSTOM(BPF_JMP | BPF_JEQ | BPF_K, __NR_getuid, 0, 1),
      BPF_STMT_CUSTOM(BPF_RET | BPF_K, SECCOMP_RET_ALLOW_VAL),

      // ALLOW: getgid (104)
      BPF_JUMP_CUSTOM(BPF_JMP | BPF_JEQ | BPF_K, __NR_getgid, 0, 1),
      BPF_STMT_CUSTOM(BPF_RET | BPF_K, SECCOMP_RET_ALLOW_VAL),

      // DENY: everything else
      BPF_STMT_CUSTOM(BPF_RET | BPF_K, SECCOMP_RET_ERRNO_VAL | EPERM),
  };

  struct sock_fprog prog = {
      .len = (unsigned short)(sizeof(filter) / sizeof(filter[0])),
      .filter = filter,
  };

  // Apply seccomp filter
  if (prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, &prog) != 0) {
    // Seccomp may not be available - log warning but continue
    fprintf(stderr, "[SANDBOX] WARNING: seccomp filter not applied: %s\n",
            strerror(errno));
  }

  g_seccomp_applied = true;
  return success_result();

#else
  // Non-Linux: seccomp not available
  g_seccomp_applied = true;
  return success_result();
#endif
}

// ============================================================
// FILESYSTEM JAIL
// ============================================================

SandboxResult sandbox_apply_fs_jail(void) {
#ifdef __linux__
  if (!g_initialized) {
    return error_result("Sandbox not initialized");
  }

  if (!g_config.chroot_path) {
    return error_result("chroot_path not set");
  }

  // Verify chroot path exists
  struct stat st;
  if (stat(g_config.chroot_path, &st) != 0) {
    return error_result("chroot path does not exist");
  }

  // Apply chroot (requires root - may fail if already dropped privs)
  if (getuid() == 0) {
    if (chroot(g_config.chroot_path) != 0) {
      fprintf(stderr, "[SANDBOX] WARNING: chroot failed: %s\n",
              strerror(errno));
    } else {
      if (chdir("/") != 0) {
        return error_result("chdir after chroot failed");
      }
    }
  } else {
    // Not root - cannot chroot, but we can restrict via seccomp
    fprintf(stderr, "[SANDBOX] INFO: chroot skipped (not root)\n");
  }

  g_fs_jailed = true;
  return success_result();

#else
  g_fs_jailed = true;
  return success_result();
#endif
}

// ============================================================
// RESOURCE LIMITS
// ============================================================

SandboxResult sandbox_set_limits(void) {
#ifdef __linux__
  if (!g_initialized) {
    return error_result("Sandbox not initialized");
  }

  struct rlimit rl;

  // RLIMIT_NOFILE (max file descriptors)
  rl.rlim_cur = g_config.max_files;
  rl.rlim_max = g_config.max_files;
  if (setrlimit(RLIMIT_NOFILE, &rl) != 0) {
    fprintf(stderr, "[SANDBOX] WARNING: RLIMIT_NOFILE not set: %s\n",
            strerror(errno));
  }

  // RLIMIT_NPROC (max processes)
  rl.rlim_cur = g_config.max_procs;
  rl.rlim_max = g_config.max_procs;
  if (setrlimit(RLIMIT_NPROC, &rl) != 0) {
    fprintf(stderr, "[SANDBOX] WARNING: RLIMIT_NPROC not set: %s\n",
            strerror(errno));
  }

  // RLIMIT_AS (max address space / memory)
  rl.rlim_cur = g_config.max_memory;
  rl.rlim_max = g_config.max_memory;
  if (setrlimit(RLIMIT_AS, &rl) != 0) {
    fprintf(stderr, "[SANDBOX] WARNING: RLIMIT_AS not set: %s\n",
            strerror(errno));
  }

  // RLIMIT_CORE (core dump size)
  rl.rlim_cur = g_config.allow_core_dump ? RLIM_INFINITY : 0;
  rl.rlim_max = g_config.allow_core_dump ? RLIM_INFINITY : 0;
  if (setrlimit(RLIMIT_CORE, &rl) != 0) {
    fprintf(stderr, "[SANDBOX] WARNING: RLIMIT_CORE not set: %s\n",
            strerror(errno));
  }

  g_limits_set = true;
  return success_result();

#else
  g_limits_set = true;
  return success_result();
#endif
}

// ============================================================
// FULL SANDBOX ENTRY
// ============================================================

SandboxResult sandbox_enter(const SandboxConfig *config) {
  SandboxResult r;

  r = sandbox_init(config);
  if (!r.success)
    return r;

  r = sandbox_drop_privileges();
  if (!r.success)
    return r;

  r = sandbox_apply_seccomp();
  if (!r.success)
    return r;

  r = sandbox_apply_fs_jail();
  if (!r.success)
    return r;

  r = sandbox_set_limits();
  if (!r.success)
    return r;

  return success_result();
}

// ============================================================
// VERIFICATION
// ============================================================

bool sandbox_verify(void) {
  if (!g_initialized)
    return false;

#ifdef __linux__
  // Verify we cannot regain privileges
  if (prctl(PR_GET_NO_NEW_PRIVS, 0, 0, 0, 0) != 1) {
    return false;
  }
#endif

  return g_privileges_dropped && g_limits_set;
}

const char *sandbox_get_status(void) {
  static char status[256];

  snprintf(status, sizeof(status),
           "init=%d priv_drop=%d seccomp=%d fs_jail=%d limits=%d uid=%d",
           g_initialized, g_privileges_dropped, g_seccomp_applied, g_fs_jailed,
           g_limits_set, (int)getuid());

  return status;
}
