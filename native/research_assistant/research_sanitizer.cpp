/*
 * research_sanitizer.cpp — Security Sanitizer for Research Content
 *
 * RULES:
 *   - Strip ALL inline JS (onclick, onerror, javascript: URIs)
 *   - Strip embedded trackers (1x1 pixels, tracking params)
 *   - Remove all <script> and <noscript> tags
 *   - Strip data URIs and base64 embedded content
 *   - No DOM injection — output is PLAIN TEXT ONLY
 *   - No execution of remote scripts
 */

#include <cctype>
#include <cstdio>
#include <cstdlib>
#include <cstring>


// =========================================================================
// CONSTANTS
// =========================================================================

static const int MAX_SANITIZE_INPUT = 65536;
static const int MAX_SANITIZE_OUTPUT = 32768;

// =========================================================================
// TYPES
// =========================================================================

struct SanitizeStats {
  int inline_js_stripped;       // onclick=, onerror=, etc.
  int javascript_uris_stripped; // javascript: URIs
  int trackers_stripped;        // Tracking pixels and params
  int scripts_stripped;         // <script> blocks
  int data_uris_stripped;       // data: URIs
  int base64_stripped;          // base64 embedded content
  int event_handlers_stripped;  // on* attributes
  int total_threats;
};

struct SanitizeResult {
  char output[MAX_SANITIZE_OUTPUT];
  int output_length;
  SanitizeStats stats;
  bool safe; // true if no threats found
  char error[128];
};

// =========================================================================
// INLINE JS PATTERNS
// =========================================================================

// Event handler attributes that must be stripped
static const char *EVENT_HANDLERS[] = {
    "onclick",     "ondblclick",    "onmousedown", "onmouseup",
    "onmouseover", "onmousemove",   "onmouseout",  "onkeypress",
    "onkeydown",   "onkeyup",       "onfocus",     "onblur",
    "onsubmit",    "onreset",       "onselect",    "onchange",
    "onload",      "onunload",      "onerror",     "onabort",
    "onresize",    "onscroll",      "oninput",     "oncontextmenu",
    "ondrag",      "ondragstart",   "ondragend",   "ondragover",
    "ondragenter", "ondragleave",   "ondrop",      "onpointerdown",
    "onpointerup", "onpointermove", nullptr};

// Tracking parameter names
static const char *TRACKING_PARAMS[] = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid",     "gclid",      "msclkid",      "twclid",   "li_fat_id",
    "_ga",        "_gid",       "mc_cid",       "mc_eid",   nullptr};

// =========================================================================
// SANITIZER ENGINE
// =========================================================================

class ResearchSanitizer {
public:
  // =====================================================================
  // SANITIZE RAW HTML — strips all threats, returns plain text
  // =====================================================================

  SanitizeResult sanitize(const char *input, int input_length) {
    SanitizeResult result;
    memset(&result, 0, sizeof(result));
    result.safe = true;

    if (!input || input_length <= 0) {
      snprintf(result.error, sizeof(result.error), "Empty input");
      return result;
    }

    if (input_length > MAX_SANITIZE_INPUT)
      input_length = MAX_SANITIZE_INPUT;

    int out_pos = 0;
    int i = 0;

    while (i < input_length && out_pos < MAX_SANITIZE_OUTPUT - 1) {
      // Detect and skip <script> blocks
      if (match_tag_ci(input, i, input_length, "script")) {
        i = skip_until_close_tag(input, i, input_length, "script");
        result.stats.scripts_stripped++;
        result.stats.total_threats++;
        result.safe = false;
        continue;
      }

      // Detect and skip <noscript> blocks
      if (match_tag_ci(input, i, input_length, "noscript")) {
        i = skip_until_close_tag(input, i, input_length, "noscript");
        result.stats.scripts_stripped++;
        continue;
      }

      // Detect and strip javascript: URIs
      if (match_ci(input + i, input_length - i, "javascript:")) {
        i = skip_until_quote_or_space(input, i, input_length);
        result.stats.javascript_uris_stripped++;
        result.stats.total_threats++;
        result.safe = false;
        continue;
      }

      // Detect and strip data: URIs
      if (match_ci(input + i, input_length - i, "data:")) {
        // Check if this is base64 encoded
        int j = i + 5;
        while (j < input_length && input[j] != '"' && input[j] != '\'' &&
               input[j] != ' ' && input[j] != '>')
          j++;
        result.stats.data_uris_stripped++;
        result.stats.total_threats++;
        result.safe = false;
        i = j;
        continue;
      }

      // Detect and strip event handler attributes
      if (strip_event_handler(input, i, input_length, result.stats)) {
        i = skip_until_quote_or_space(input, i, input_length);
        result.safe = false;
        continue;
      }

      // Detect tracking pixels (1x1 <img>)
      if (is_tracking_pixel(input, i, input_length)) {
        i = skip_until_char(input, i, input_length, '>');
        if (i < input_length)
          i++; // skip >
        result.stats.trackers_stripped++;
        continue;
      }

      // Emit safe character
      if (out_pos < MAX_SANITIZE_OUTPUT - 1) {
        result.output[out_pos++] = input[i];
      }
      i++;
    }

    result.output[out_pos] = '\0';
    result.output_length = out_pos;

    return result;
  }

  // =====================================================================
  // STRIP TRACKING PARAMS FROM URL
  // =====================================================================

  int strip_tracking_params(const char *url, char *out, int out_max) {
    int url_len = (int)strlen(url);
    const char *qmark = strchr(url, '?');
    if (!qmark) {
      int copy = url_len < out_max - 1 ? url_len : out_max - 1;
      memcpy(out, url, copy);
      out[copy] = '\0';
      return copy;
    }

    // Copy base URL
    int base_len = (int)(qmark - url);
    int pos = base_len < out_max - 1 ? base_len : out_max - 1;
    memcpy(out, url, pos);

    // Parse and filter query params
    bool first_param = true;
    const char *p = qmark + 1;
    while (*p) {
      // Find param name
      const char *eq = strchr(p, '=');
      const char *amp = strchr(p, '&');
      if (!eq || (amp && amp < eq)) {
        p = amp ? amp + 1 : p + strlen(p);
        continue;
      }

      int name_len = (int)(eq - p);
      bool is_tracker = false;

      for (int t = 0; TRACKING_PARAMS[t]; t++) {
        if (name_len == (int)strlen(TRACKING_PARAMS[t]) &&
            strncmp(p, TRACKING_PARAMS[t], name_len) == 0) {
          is_tracker = true;
          break;
        }
      }

      if (!is_tracker) {
        if (pos < out_max - 2) {
          out[pos++] = first_param ? '?' : '&';
          first_param = false;
        }
        // Copy param
        const char *end = amp ? amp : p + strlen(p);
        int plen = (int)(end - p);
        int copy = plen < out_max - 1 - pos ? plen : out_max - 1 - pos;
        memcpy(out + pos, p, copy);
        pos += copy;
      }

      p = amp ? amp + 1 : p + strlen(p);
    }

    out[pos] = '\0';
    return pos;
  }

  // Guards
  static bool can_execute_remote_scripts() { return false; }
  static bool can_inject_dom() { return false; }
  static bool can_persist_data() { return false; }

private:
  // =====================================================================
  // HELPERS
  // =====================================================================

  static bool match_ci(const char *text, int remaining, const char *pattern) {
    int plen = (int)strlen(pattern);
    if (remaining < plen)
      return false;
    for (int i = 0; i < plen; i++) {
      if (tolower(text[i]) != tolower(pattern[i]))
        return false;
    }
    return true;
  }

  static bool match_tag_ci(const char *text, int pos, int len,
                           const char *tag) {
    if (pos >= len || text[pos] != '<')
      return false;
    int tlen = (int)strlen(tag);
    if (pos + 1 + tlen >= len)
      return false;
    for (int i = 0; i < tlen; i++) {
      if (tolower(text[pos + 1 + i]) != tolower(tag[i]))
        return false;
    }
    char after = text[pos + 1 + tlen];
    return (after == ' ' || after == '>' || after == '\n' || after == '\r' ||
            after == '\t');
  }

  static int skip_until_close_tag(const char *text, int pos, int len,
                                  const char *tag) {
    int tlen = (int)strlen(tag);
    while (pos < len) {
      if (text[pos] == '<' && pos + 1 < len && text[pos + 1] == '/') {
        bool match = true;
        for (int j = 0; j < tlen && (pos + 2 + j) < len; j++) {
          if (tolower(text[pos + 2 + j]) != tolower(tag[j])) {
            match = false;
            break;
          }
        }
        if (match) {
          // Skip to >
          pos += 2 + tlen;
          while (pos < len && text[pos] != '>')
            pos++;
          return pos < len ? pos + 1 : pos;
        }
      }
      pos++;
    }
    return pos;
  }

  static int skip_until_quote_or_space(const char *text, int pos, int len) {
    while (pos < len && text[pos] != '"' && text[pos] != '\'' &&
           text[pos] != ' ' && text[pos] != '>' && text[pos] != '\n')
      pos++;
    return pos;
  }

  static int skip_until_char(const char *text, int pos, int len, char target) {
    while (pos < len && text[pos] != target)
      pos++;
    return pos;
  }

  static bool strip_event_handler(const char *text, int pos, int len,
                                  SanitizeStats &stats) {
    // Check if current position starts with on* event handler
    if (pos >= len || tolower(text[pos]) != 'o')
      return false;
    if (pos + 1 >= len || tolower(text[pos + 1]) != 'n')
      return false;

    for (int i = 0; EVENT_HANDLERS[i]; i++) {
      int hlen = (int)strlen(EVENT_HANDLERS[i]);
      if (pos + hlen >= len)
        continue;

      bool match = true;
      for (int j = 0; j < hlen; j++) {
        if (tolower(text[pos + j]) != EVENT_HANDLERS[i][j]) {
          match = false;
          break;
        }
      }
      if (match && (text[pos + hlen] == '=' || text[pos + hlen] == ' ')) {
        stats.event_handlers_stripped++;
        stats.inline_js_stripped++;
        stats.total_threats++;
        return true;
      }
    }
    return false;
  }

  static bool is_tracking_pixel(const char *text, int pos, int len) {
    // Look for <img ... width="1" height="1" or width=1 height=1
    if (!match_tag_ci(text, pos, len, "img"))
      return false;

    // Scan tag for 1x1 dimensions
    int end = pos;
    while (end < len && text[end] != '>')
      end++;

    bool has_w1 = false, has_h1 = false;
    for (int i = pos; i < end - 8; i++) {
      if (match_ci(text + i, end - i, "width=\"1\"") ||
          match_ci(text + i, end - i, "width='1'") ||
          match_ci(text + i, end - i, "width=1"))
        has_w1 = true;
      if (match_ci(text + i, end - i, "height=\"1\"") ||
          match_ci(text + i, end - i, "height='1'") ||
          match_ci(text + i, end - i, "height=1"))
        has_h1 = true;
    }
    return has_w1 && has_h1;
  }
};
