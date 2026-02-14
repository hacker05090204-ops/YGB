/*
 * content_extractor.cpp — HTML-to-Text Extraction Engine
 *
 * RULES:
 *   - Drops <script>, <style>, <iframe>, <object>, <embed> blocks completely
 *   - Extracts visible text from <p>, <h1-h6>, <li>, <td>, <span>, <div>
 *   - No DOM construction — single-pass state machine
 *   - Max 4KB output per page
 *   - No remote resource loading
 *   - No execution of any embedded code
 */

#include <cctype>
#include <cstdio>
#include <cstdlib>
#include <cstring>


// =========================================================================
// CONSTANTS
// =========================================================================

static const int MAX_INPUT_BYTES = 65536; // 64KB max HTML input
static const int MAX_OUTPUT_BYTES = 4096; // 4KB max text output
static const int MAX_TAG_LENGTH = 64;
static const int MAX_SECTIONS = 64;

// =========================================================================
// TYPES
// =========================================================================

enum class ParserState {
  TEXT,       // Inside visible text
  TAG_OPEN,   // Reading tag name after <
  TAG_CLOSE,  // Reading close tag name after </
  INSIDE_TAG, // Inside tag attributes (skip)
  SKIP_BLOCK, // Inside <script>, <style>, etc. (skip entirely)
  COMMENT,    // Inside <!-- -->
  ENTITY,     // Inside &entity;
};

enum class ContentType {
  HEADING,
  PARAGRAPH,
  LIST_ITEM,
  TABLE_CELL,
  GENERIC_TEXT,
};

struct ExtractedSection {
  ContentType type;
  char text[512];
  int text_length;
};

struct ExtractionResult {
  ExtractedSection sections[MAX_SECTIONS];
  int section_count;
  char full_text[MAX_OUTPUT_BYTES];
  int full_text_length;
  int tags_stripped;
  int scripts_dropped;
  int styles_dropped;
  bool success;
  char error[128];
};

// =========================================================================
// TAG CLASSIFICATION
// =========================================================================

// Tags whose content should be completely dropped
static bool is_drop_tag(const char *tag) {
  static const char *DROP_TAGS[] = {"script", "style",    "iframe",   "object",
                                    "embed",  "noscript", "template", "svg",
                                    "canvas", nullptr};
  for (int i = 0; DROP_TAGS[i]; i++) {
    if (strcasecmp(tag, DROP_TAGS[i]) == 0)
      return true;
  }
  return false;
}

// Cross-platform strcasecmp
#ifdef _WIN32
#define strcasecmp _stricmp
#endif

// Tags that represent content blocks (add newline after)
static bool is_block_tag(const char *tag) {
  static const char *BLOCK_TAGS[] = {
      "p",          "div",        "h1",      "h2",      "h3",     "h4",
      "h5",         "h6",         "li",      "tr",      "br",     "hr",
      "blockquote", "pre",        "article", "section", "header", "footer",
      "main",       "figcaption", "summary", "details", nullptr};
  for (int i = 0; BLOCK_TAGS[i]; i++) {
    if (strcasecmp(tag, BLOCK_TAGS[i]) == 0)
      return true;
  }
  return false;
}

// Tags that produce inline content
static ContentType classify_tag(const char *tag) {
  if (tag[0] == 'h' && tag[1] >= '1' && tag[1] <= '6' && tag[2] == '\0')
    return ContentType::HEADING;
  if (strcasecmp(tag, "p") == 0)
    return ContentType::PARAGRAPH;
  if (strcasecmp(tag, "li") == 0)
    return ContentType::LIST_ITEM;
  if (strcasecmp(tag, "td") == 0 || strcasecmp(tag, "th") == 0)
    return ContentType::TABLE_CELL;
  return ContentType::GENERIC_TEXT;
}

// =========================================================================
// HTML ENTITY DECODER (minimal)
// =========================================================================

static char decode_entity(const char *entity, int len) {
  if (len <= 0)
    return ' ';
  char buf[16];
  int copy_len = len < 15 ? len : 15;
  memcpy(buf, entity, copy_len);
  buf[copy_len] = '\0';

  if (strcmp(buf, "amp") == 0)
    return '&';
  if (strcmp(buf, "lt") == 0)
    return '<';
  if (strcmp(buf, "gt") == 0)
    return '>';
  if (strcmp(buf, "quot") == 0)
    return '"';
  if (strcmp(buf, "apos") == 0)
    return '\'';
  if (strcmp(buf, "nbsp") == 0)
    return ' ';
  if (buf[0] == '#') {
    int code = atoi(buf + 1);
    if (code > 0 && code < 128)
      return (char)code;
  }
  return ' ';
}

// =========================================================================
// CONTENT EXTRACTOR
// =========================================================================

class ContentExtractor {
public:
  ExtractionResult extract(const char *html, int html_length) {
    ExtractionResult result;
    memset(&result, 0, sizeof(result));
    result.success = true;

    if (!html || html_length <= 0) {
      result.success = false;
      snprintf(result.error, sizeof(result.error), "Empty HTML input");
      return result;
    }

    if (html_length > MAX_INPUT_BYTES) {
      html_length = MAX_INPUT_BYTES;
    }

    ParserState state = ParserState::TEXT;
    char current_tag[MAX_TAG_LENGTH];
    int tag_pos = 0;
    char skip_until_tag[MAX_TAG_LENGTH];
    skip_until_tag[0] = '\0';
    int comment_dashes = 0;

    char entity_buf[16];
    int entity_pos = 0;

    // Current section being built
    ContentType current_type = ContentType::GENERIC_TEXT;
    char section_buf[512];
    int section_pos = 0;

    // Output buffer
    int out_pos = 0;

    auto flush_section = [&]() {
      if (section_pos > 0 && result.section_count < MAX_SECTIONS) {
        // Trim trailing whitespace
        while (section_pos > 0 && (section_buf[section_pos - 1] == ' ' ||
                                   section_buf[section_pos - 1] == '\n' ||
                                   section_buf[section_pos - 1] == '\r' ||
                                   section_buf[section_pos - 1] == '\t'))
          section_pos--;

        if (section_pos > 0) {
          section_buf[section_pos] = '\0';
          ExtractedSection &s = result.sections[result.section_count++];
          s.type = current_type;
          strncpy(s.text, section_buf, 511);
          s.text[511] = '\0';
          s.text_length = section_pos;

          // Append to full text
          if (out_pos + section_pos + 2 < MAX_OUTPUT_BYTES) {
            memcpy(result.full_text + out_pos, section_buf, section_pos);
            out_pos += section_pos;
            result.full_text[out_pos++] = '\n';
          }
        }
        section_pos = 0;
      }
    };

    auto emit_char = [&](char c) {
      // Normalize whitespace
      if (c == '\r' || c == '\t')
        c = ' ';
      // Collapse multiple spaces
      if (c == ' ' && section_pos > 0 && section_buf[section_pos - 1] == ' ')
        return;
      if (section_pos < 510) {
        section_buf[section_pos++] = c;
      }
    };

    for (int i = 0; i < html_length; i++) {
      char c = html[i];

      switch (state) {
      case ParserState::TEXT:
        if (c == '<') {
          state = ParserState::TAG_OPEN;
          tag_pos = 0;
          current_tag[0] = '\0';
        } else if (c == '&') {
          state = ParserState::ENTITY;
          entity_pos = 0;
        } else {
          emit_char(c);
        }
        break;

      case ParserState::TAG_OPEN:
        if (c == '/') {
          state = ParserState::TAG_CLOSE;
          tag_pos = 0;
        } else if (c == '!') {
          // Check for comment
          if (i + 2 < html_length && html[i + 1] == '-' && html[i + 2] == '-') {
            state = ParserState::COMMENT;
            comment_dashes = 0;
            i += 2;
          } else {
            state = ParserState::INSIDE_TAG;
          }
        } else if (c == '>' || c == ' ' || c == '\n' || c == '\r') {
          current_tag[tag_pos] = '\0';
          result.tags_stripped++;

          if (is_drop_tag(current_tag)) {
            state = ParserState::SKIP_BLOCK;
            strncpy(skip_until_tag, current_tag, MAX_TAG_LENGTH - 1);
            if (strcasecmp(current_tag, "script") == 0)
              result.scripts_dropped++;
            if (strcasecmp(current_tag, "style") == 0)
              result.styles_dropped++;
          } else {
            if (is_block_tag(current_tag)) {
              flush_section();
              current_type = classify_tag(current_tag);
            }
            state = (c == '>') ? ParserState::TEXT : ParserState::INSIDE_TAG;
          }
        } else if (tag_pos < MAX_TAG_LENGTH - 1) {
          current_tag[tag_pos++] = (char)tolower(c);
        }
        break;

      case ParserState::TAG_CLOSE:
        if (c == '>') {
          current_tag[tag_pos] = '\0';
          if (is_block_tag(current_tag)) {
            flush_section();
          }
          state = ParserState::TEXT;
          result.tags_stripped++;
        } else if (tag_pos < MAX_TAG_LENGTH - 1) {
          current_tag[tag_pos++] = (char)tolower(c);
        }
        break;

      case ParserState::INSIDE_TAG:
        if (c == '>') {
          state = ParserState::TEXT;
        }
        // Skip all attributes
        break;

      case ParserState::SKIP_BLOCK:
        // Look for closing tag </script>, </style>, etc.
        if (c == '<' && i + 1 < html_length && html[i + 1] == '/') {
          // Check if this closes the skip block
          int slen = (int)strlen(skip_until_tag);
          bool match = true;
          for (int j = 0; j < slen && (i + 2 + j) < html_length; j++) {
            if (tolower(html[i + 2 + j]) != tolower(skip_until_tag[j])) {
              match = false;
              break;
            }
          }
          if (match && (i + 2 + slen) < html_length &&
              (html[i + 2 + slen] == '>' || html[i + 2 + slen] == ' ')) {
            // Skip to end of closing tag
            i += 2 + slen;
            while (i < html_length && html[i] != '>')
              i++;
            state = ParserState::TEXT;
          }
        }
        break;

      case ParserState::COMMENT:
        if (c == '-') {
          comment_dashes++;
        } else if (c == '>' && comment_dashes >= 2) {
          state = ParserState::TEXT;
          comment_dashes = 0;
        } else {
          comment_dashes = 0;
        }
        break;

      case ParserState::ENTITY:
        if (c == ';') {
          emit_char(decode_entity(entity_buf, entity_pos));
          state = ParserState::TEXT;
        } else if (entity_pos < 14) {
          entity_buf[entity_pos++] = c;
        } else {
          // Malformed entity, dump as text
          emit_char('&');
          for (int j = 0; j < entity_pos; j++)
            emit_char(entity_buf[j]);
          emit_char(c);
          state = ParserState::TEXT;
        }
        break;
      }
    }

    // Flush remaining section
    flush_section();

    result.full_text[out_pos] = '\0';
    result.full_text_length = out_pos;

    return result;
  }

  // Guards — research mode restrictions
  static bool can_execute_scripts() { return false; }
  static bool can_load_remote_resources() { return false; }
  static bool can_inject_dom() { return false; }
  static bool can_access_training_data() { return false; }
};
