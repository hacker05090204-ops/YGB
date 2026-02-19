/**
 * storage_abuse_detector.cpp — Client Storage Abuse Detection
 *
 * Detects misuse of client-side storage:
 *   - Sensitive data in localStorage/sessionStorage
 *   - Auth tokens in unencrypted storage
 *   - Cookie flags missing (HTTPOnly, Secure, SameSite)
 *   - IndexedDB sensitive data exposure
 *   - Cache poisoning opportunities
 *
 * Field 1: Client-Side Web Application Security
 */

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>


namespace client_side {

// =========================================================================
// STORAGE ABUSE RESULT
// =========================================================================

struct StorageAbuseResult {
  uint32_t local_storage_sensitive;
  uint32_t session_storage_sensitive;
  uint32_t unprotected_tokens;
  uint32_t cookies_missing_httponly;
  uint32_t cookies_missing_secure;
  uint32_t cookies_missing_samesite;
  uint32_t indexeddb_exposure;
  uint32_t cache_poison_points;
  double storage_risk; // 0.0–1.0
  bool critical;
};

// =========================================================================
// STORAGE ABUSE DETECTOR
// =========================================================================

class StorageAbuseDetector {
public:
  StorageAbuseResult analyze(uint32_t ls_sensitive, uint32_t ss_sensitive,
                             uint32_t unprotected_tokens, uint32_t no_httponly,
                             uint32_t no_secure, uint32_t no_samesite,
                             uint32_t idb_exposure, uint32_t cache_poison) {
    StorageAbuseResult r;
    std::memset(&r, 0, sizeof(r));

    r.local_storage_sensitive = ls_sensitive;
    r.session_storage_sensitive = ss_sensitive;
    r.unprotected_tokens = unprotected_tokens;
    r.cookies_missing_httponly = no_httponly;
    r.cookies_missing_secure = no_secure;
    r.cookies_missing_samesite = no_samesite;
    r.indexeddb_exposure = idb_exposure;
    r.cache_poison_points = cache_poison;

    double weighted = unprotected_tokens * 4.0 + ls_sensitive * 3.0 +
                      no_httponly * 2.5 + no_secure * 2.5 + ss_sensitive * 2.0 +
                      idb_exposure * 2.0 + cache_poison * 1.5 +
                      no_samesite * 1.0;
    uint32_t total = ls_sensitive + ss_sensitive + unprotected_tokens +
                     no_httponly + no_secure + no_samesite + idb_exposure +
                     cache_poison;
    double max_w = (total > 0) ? total * 4.0 : 1.0;
    r.storage_risk = std::fmin(weighted / max_w, 1.0);
    r.critical = (unprotected_tokens > 0) || (r.storage_risk > 0.7);

    return r;
  }
};

} // namespace client_side
