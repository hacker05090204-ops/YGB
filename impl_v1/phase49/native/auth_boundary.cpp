// auth_boundary.cpp
// Phase-49: Auth Boundary Detection Implementation

#include "auth_boundary.h"
#include <algorithm>
#include <cstring>
#include <regex>

namespace phase49 {

AuthBoundaryDetector::AuthBoundaryDetector() : initialized_(false) {}

AuthBoundaryDetector::~AuthBoundaryDetector() = default;

bool AuthBoundaryDetector::initialize() {
  initialized_ = true;
  return true;
}

bool AuthBoundaryDetector::has_login_form(const std::string &html) const {
  // Look for common login form patterns
  std::vector<std::string> patterns = {"type=\"password\"", "type='password'",
                                       "name=\"password\"", "name=\"passwd\"",
                                       "id=\"password\"",   "class=\"login",
                                       "class=\"signin",    "action=\"/login",
                                       "action=\"/signin",  "action=\"/auth"};

  std::string lower_html = html;
  std::transform(lower_html.begin(), lower_html.end(), lower_html.begin(),
                 ::tolower);

  for (const auto &pattern : patterns) {
    if (lower_html.find(pattern) != std::string::npos) {
      return true;
    }
  }

  return false;
}

bool AuthBoundaryDetector::has_password_field(const std::string &html) const {
  std::regex password_regex("<input[^>]*type=[\"']password[\"'][^>]*>",
                            std::regex::icase);
  return std::regex_search(html, password_regex);
}

bool AuthBoundaryDetector::is_oauth_redirect(const std::string &url) const {
  std::vector<std::string> oauth_indicators = {"oauth",
                                               "authorize",
                                               "auth/login",
                                               "accounts.google.com",
                                               "login.microsoftonline",
                                               "github.com/login",
                                               "facebook.com/login"};

  std::string lower_url = url;
  std::transform(lower_url.begin(), lower_url.end(), lower_url.begin(),
                 ::tolower);

  for (const auto &indicator : oauth_indicators) {
    if (lower_url.find(indicator) != std::string::npos) {
      return true;
    }
  }

  return false;
}

bool AuthBoundaryDetector::is_login_path(const std::string &url) const {
  std::vector<std::string> login_paths = {
      "/login",       "/signin",        "/sign-in",
      "/auth",        "/account/login", "/user/login",
      "/session/new", "/sso",           "/authenticate"};

  std::string lower_url = url;
  std::transform(lower_url.begin(), lower_url.end(), lower_url.begin(),
                 ::tolower);

  for (const auto &path : login_paths) {
    if (lower_url.find(path) != std::string::npos) {
      return true;
    }
  }

  return false;
}

AuthBoundaryResult
AuthBoundaryDetector::detect_from_html(const std::string &html) {
  AuthBoundaryResult result;
  result.auth_required = false;
  result.type = AuthBoundaryType::NONE;

  // Check for password field
  if (has_password_field(html)) {
    result.auth_required = true;
    result.type = AuthBoundaryType::LOGIN_FORM;
    result.reason = "Password input field detected";

    // Extract form fields
    std::regex field_regex("<input[^>]*name=[\"']([^\"']+)[\"'][^>]*>",
                           std::regex::icase);
    std::sregex_iterator it(html.begin(), html.end(), field_regex);
    std::sregex_iterator end;

    while (it != end) {
      result.form_fields.push_back((*it)[1].str());
      ++it;
    }

    return result;
  }

  // Check for login form patterns
  if (has_login_form(html)) {
    result.auth_required = true;
    result.type = AuthBoundaryType::LOGIN_FORM;
    result.reason = "Login form detected";
    return result;
  }

  return result;
}

AuthBoundaryResult AuthBoundaryDetector::detect_from_response(
    int status_code, const std::string &headers, const std::string &body) {
  AuthBoundaryResult result;
  result.auth_required = false;
  result.type = AuthBoundaryType::NONE;

  // Check status code
  if (status_code == 401) {
    result.auth_required = true;
    result.type = AuthBoundaryType::BASIC_AUTH;
    result.reason = "HTTP 401 Unauthorized";
    return result;
  }

  if (status_code == 403) {
    result.auth_required = true;
    result.type = AuthBoundaryType::API_KEY;
    result.reason = "HTTP 403 Forbidden - may require API key";
    return result;
  }

  // Check for redirect to OAuth
  if (status_code >= 300 && status_code < 400) {
    std::regex location_regex("Location:\\s*([^\\r\\n]+)", std::regex::icase);
    std::smatch match;
    if (std::regex_search(headers, match, location_regex)) {
      std::string redirect_url = match[1].str();
      if (is_oauth_redirect(redirect_url)) {
        result.auth_required = true;
        result.type = AuthBoundaryType::OAUTH;
        result.redirect_url = redirect_url;
        result.reason = "OAuth redirect detected";
        return result;
      }
    }
  }

  // Check body
  if (!body.empty()) {
    return detect_from_html(body);
  }

  return result;
}

// C interface
extern "C" {

void *auth_boundary_create() { return new AuthBoundaryDetector(); }

void auth_boundary_destroy(void *detector) {
  delete static_cast<AuthBoundaryDetector *>(detector);
}

int auth_boundary_init(void *detector) {
  if (!detector)
    return -1;
  return static_cast<AuthBoundaryDetector *>(detector)->initialize() ? 0 : -1;
}

int auth_boundary_detect(void *detector, const char *html,
                         int *out_auth_required, int *out_type,
                         char *out_reason, int reason_size) {
  if (!detector || !html)
    return -1;

  AuthBoundaryResult result =
      static_cast<AuthBoundaryDetector *>(detector)->detect_from_html(html);

  if (out_auth_required)
    *out_auth_required = result.auth_required ? 1 : 0;
  if (out_type)
    *out_type = static_cast<int>(result.type);
  if (out_reason && reason_size > 0) {
    strncpy(out_reason, result.reason.c_str(), reason_size - 1);
    out_reason[reason_size - 1] = '\0';
  }

  return 0;
}

} // extern "C"

} // namespace phase49
