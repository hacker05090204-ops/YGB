// auth_boundary.h
// Phase-49: Auth Boundary Detection
//
// STRICT RULES:
// - Detect login walls ONLY
// - NO bypass logic
// - NO credential handling

#ifndef PHASE49_AUTH_BOUNDARY_H
#define PHASE49_AUTH_BOUNDARY_H

#include <string>
#include <vector>

namespace phase49 {

// Auth boundary type
enum class AuthBoundaryType {
  NONE,           // No auth required
  LOGIN_FORM,     // Standard login form
  OAUTH,          // OAuth redirect
  BASIC_AUTH,     // HTTP Basic Auth
  API_KEY,        // API key required
  SESSION_EXPIRED // Session expired
};

// Detection result
struct AuthBoundaryResult {
  bool auth_required;
  AuthBoundaryType type;
  std::string reason;
  std::string redirect_url;
  std::vector<std::string> form_fields; // Detected form fields
};

// Auth boundary detector
class AuthBoundaryDetector {
public:
  AuthBoundaryDetector();
  ~AuthBoundaryDetector();

  bool initialize();

  // Detect auth boundary from HTML
  AuthBoundaryResult detect_from_html(const std::string &html);

  // Detect from HTTP response
  AuthBoundaryResult detect_from_response(int status_code,
                                          const std::string &headers,
                                          const std::string &body);

  // Check if URL is a known login path
  bool is_login_path(const std::string &url) const;

private:
  bool initialized_;

  // Detection helpers
  bool has_login_form(const std::string &html) const;
  bool has_password_field(const std::string &html) const;
  bool is_oauth_redirect(const std::string &url) const;
};

// C interface
extern "C" {
void *auth_boundary_create();
void auth_boundary_destroy(void *detector);
int auth_boundary_init(void *detector);
int auth_boundary_detect(void *detector, const char *html,
                         int *out_auth_required, int *out_type,
                         char *out_reason, int reason_size);
}

} // namespace phase49

#endif // PHASE49_AUTH_BOUNDARY_H
