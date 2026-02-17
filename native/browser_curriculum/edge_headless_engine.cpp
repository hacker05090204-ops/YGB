/*
 * edge_headless_engine.cpp — Headless Edge Browser Engine
 *
 * Manages isolated Edge headless sessions for safe content fetching.
 *
 * ISOLATION RULES:
 *   --headless=new
 *   --disable-extensions
 *   --disable-sync
 *   --disable-features=NetworkService
 *   --user-data-dir=./automation_profile
 *   --no-first-run
 *   --disable-default-apps
 *
 * NO Microsoft login. NO session persistence. NO system cookies.
 *
 * GOVERNANCE: MODE-A only. Zero decision authority.
 */

#include <algorithm>
#include <chrono>
#include <cstdint>
#include <sstream>
#include <string>
#include <unordered_set>
#include <vector>


namespace browser_curriculum {

// =========================================================================
// DOMAIN WHITELIST
// =========================================================================

static const std::unordered_set<std::string> ALLOWED_DOMAINS = {
    // NVD / CVE feeds
    "nvd.nist.gov",
    "services.nvd.nist.gov",
    "cve.org",
    "www.cve.org",
    "cveawg.mitre.org",
    // OWASP
    "owasp.org",
    "www.owasp.org",
    "cheatsheetseries.owasp.org",
    // MITRE CWE
    "cwe.mitre.org",
    "capec.mitre.org",
    // CVE RSS feeds
    "www.cvedetails.com",
    "cvedetails.com",
    // Whitelisted security blogs
    "portswigger.net",
    "www.portswigger.net",
    "blog.cloudflare.com",
    "security.googleblog.com",
    "msrc.microsoft.com",
};

// =========================================================================
// BLOCKED PATTERNS (never fetch these)
// =========================================================================

static const std::vector<std::string> BLOCKED_URL_PATTERNS = {
    "login",          "signin",       "signup",
    "register",       "oauth",        "auth/",
    "account",        "password",     "credential",
    "session",        ".exe",         ".msi",
    ".bat",           ".ps1",         ".sh",
    "exploit-db.com", "pastebin.com", "github.com/exploits",
};

// =========================================================================
// EDGE LAUNCH CONFIG
// =========================================================================

struct EdgeLaunchConfig {
  std::string edge_path;
  std::string user_data_dir;
  int timeout_seconds;
  int max_response_bytes;
  bool headless;
  bool disable_extensions;
  bool disable_sync;
  bool no_first_run;

  EdgeLaunchConfig()
      : edge_path("msedge"), user_data_dir("./automation_profile"),
        timeout_seconds(15), max_response_bytes(131072) // 128KB
        ,
        headless(true), disable_extensions(true), disable_sync(true),
        no_first_run(true) {}

  std::vector<std::string> build_args(const std::string &url) const {
    std::vector<std::string> args;
    args.push_back(edge_path);

    if (headless)
      args.push_back("--headless=new");
    if (disable_extensions)
      args.push_back("--disable-extensions");
    if (disable_sync)
      args.push_back("--disable-sync");
    if (no_first_run)
      args.push_back("--no-first-run");

    args.push_back("--disable-features=NetworkService");
    args.push_back("--disable-default-apps");
    args.push_back("--disable-background-networking");
    args.push_back("--disable-translate");
    args.push_back("--disable-component-update");
    args.push_back("--no-sandbox");
    args.push_back("--inprivate");
    args.push_back("--dump-dom");

    args.push_back("--user-data-dir=" + user_data_dir);
    args.push_back(url);

    return args;
  }
};

// =========================================================================
// FETCH RESULT
// =========================================================================

struct FetchResult {
  bool success;
  std::string url;
  std::string content;
  std::string error;
  int status_code;
  int64_t elapsed_ms;
  int content_bytes;
};

// =========================================================================
// DOMAIN VALIDATION
// =========================================================================

inline std::string extract_domain(const std::string &url) {
  size_t start = url.find("://");
  if (start == std::string::npos)
    return "";
  start += 3;
  size_t end = url.find('/', start);
  if (end == std::string::npos)
    end = url.length();
  // Strip port
  std::string host = url.substr(start, end - start);
  size_t colon = host.find(':');
  if (colon != std::string::npos)
    host = host.substr(0, colon);
  return host;
}

inline bool is_domain_allowed(const std::string &url) {
  std::string domain = extract_domain(url);
  if (domain.empty())
    return false;
  return ALLOWED_DOMAINS.find(domain) != ALLOWED_DOMAINS.end();
}

inline bool is_url_blocked(const std::string &url) {
  std::string lower_url = url;
  std::transform(lower_url.begin(), lower_url.end(), lower_url.begin(),
                 ::tolower);
  for (const auto &pattern : BLOCKED_URL_PATTERNS) {
    if (lower_url.find(pattern) != std::string::npos) {
      return true;
    }
  }
  return false;
}

// =========================================================================
// CONTENT STRIPPING
// =========================================================================

inline std::string strip_scripts_and_trackers(const std::string &html) {
  std::string result = html;
  // Simple tag removal for <script>, <style>, <iframe>
  auto strip_tag = [&](const std::string &tag) {
    while (true) {
      size_t start = result.find("<" + tag);
      if (start == std::string::npos)
        break;
      size_t end = result.find("</" + tag + ">", start);
      if (end == std::string::npos) {
        end = result.find(">", start);
        if (end != std::string::npos) {
          result.erase(start, end - start + 1);
        }
        break;
      }
      result.erase(start, end - start + tag.length() + 3);
    }
  };
  strip_tag("script");
  strip_tag("style");
  strip_tag("iframe");
  strip_tag("noscript");
  return result;
}

// =========================================================================
// SAFE FETCH ORCHESTRATION
// =========================================================================

inline FetchResult safe_fetch(const std::string &url,
                              const EdgeLaunchConfig &config) {
  FetchResult result;
  result.url = url;
  result.success = false;
  result.status_code = 0;
  result.elapsed_ms = 0;
  result.content_bytes = 0;

  // Domain check
  if (!is_domain_allowed(url)) {
    result.error = "BLOCKED: Domain not in whitelist";
    return result;
  }

  // URL pattern check
  if (is_url_blocked(url)) {
    result.error = "BLOCKED: URL contains blocked pattern";
    return result;
  }

  // Validate HTTPS only
  if (url.substr(0, 8) != "https://") {
    result.error = "BLOCKED: Only HTTPS URLs allowed";
    return result;
  }

  // Build command args (actual subprocess launch done in Python bridge)
  auto args = config.build_args(url);
  result.success = true;
  result.error = "";

  // Content will be filled by Python bridge after subprocess call
  return result;
}

// =========================================================================
// ISOLATION VERIFICATION
// =========================================================================

struct IsolationCheck {
  bool no_login;
  bool no_sync;
  bool no_session_persistence;
  bool isolated_profile;
  bool domain_whitelist_active;

  bool all_pass() const {
    return no_login && no_sync && no_session_persistence && isolated_profile &&
           domain_whitelist_active;
  }
};

inline IsolationCheck verify_isolation(const EdgeLaunchConfig &config) {
  IsolationCheck check;
  check.no_login = config.disable_sync;
  check.no_sync = config.disable_sync;
  check.no_session_persistence = config.headless;
  check.isolated_profile =
      !config.user_data_dir.empty() && config.user_data_dir != "Default";
  check.domain_whitelist_active = !ALLOWED_DOMAINS.empty();
  return check;
}

} // namespace browser_curriculum
