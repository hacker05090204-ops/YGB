// dom_diff_engine.cpp
// Phase-49: DOM Diff Engine Implementation

#include "dom_diff_engine.h"
#include <algorithm>
#include <cstring>
#include <regex>
#include <sstream>

namespace phase49 {

DOMDiffEngine::DOMDiffEngine() : initialized_(false) {}

DOMDiffEngine::~DOMDiffEngine() = default;

bool DOMDiffEngine::initialize() {
  initialized_ = true;
  return true;
}

DOMNode DOMDiffEngine::parse_html(const std::string &html) {
  DOMNode root;
  root.type = DOMNodeType::DOCUMENT;
  root.tag_name = "document";

  // Simple HTML parser
  // In production, use libxml2 or similar
  std::regex tag_regex("<([a-zA-Z0-9]+)([^>]*)>([^<]*)</\\1>|"
                       "<([a-zA-Z0-9]+)([^>]*)/>|"
                       "<([a-zA-Z0-9]+)([^>]*)>");
  std::regex attr_regex("([a-zA-Z-]+)=\"([^\"]*)\"");

  std::string remaining = html;
  size_t pos = 0;

  while (pos < remaining.size()) {
    // Find next tag
    size_t tag_start = remaining.find('<', pos);
    if (tag_start == std::string::npos)
      break;

    // Extract text before tag
    if (tag_start > pos) {
      DOMNode text_node;
      text_node.type = DOMNodeType::TEXT;
      text_node.text_content = remaining.substr(pos, tag_start - pos);
      if (!text_node.text_content.empty() &&
          text_node.text_content.find_first_not_of(" \t\n\r") !=
              std::string::npos) {
        root.children.push_back(text_node);
      }
    }

    // Find tag end
    size_t tag_end = remaining.find('>', tag_start);
    if (tag_end == std::string::npos)
      break;

    std::string tag = remaining.substr(tag_start, tag_end - tag_start + 1);

    // Skip closing tags
    if (tag[1] == '/') {
      pos = tag_end + 1;
      continue;
    }

    // Parse tag
    DOMNode element;
    element.type = DOMNodeType::ELEMENT;

    // Extract tag name
    size_t name_end = tag.find_first_of(" />", 1);
    element.tag_name = tag.substr(1, name_end - 1);

    // Extract attributes
    std::sregex_iterator attr_it(tag.begin(), tag.end(), attr_regex);
    std::sregex_iterator attr_end;
    for (; attr_it != attr_end; ++attr_it) {
      std::string attr_name = (*attr_it)[1].str();
      std::string attr_value = (*attr_it)[2].str();
      element.attributes.push_back({attr_name, attr_value});

      if (attr_name == "id") {
        element.id = attr_value;
      } else if (attr_name == "class") {
        element.class_name = attr_value;
      }
    }

    root.children.push_back(element);
    pos = tag_end + 1;
  }

  return root;
}

int DOMDiffEngine::count_nodes(const DOMNode &node) const {
  int count = 1;
  for (const auto &child : node.children) {
    count += count_nodes(child);
  }
  return count;
}

void DOMDiffEngine::diff_nodes(const DOMNode &before, const DOMNode &after,
                               const std::string &path,
                               std::vector<DiffEntry> &changes) {
  // Check if nodes are different
  if (before.tag_name != after.tag_name) {
    DiffEntry entry;
    entry.operation = DiffOpType::MODIFIED;
    entry.path = path;
    entry.old_value = before.tag_name;
    entry.new_value = after.tag_name;
    entry.tag_name = after.tag_name;
    changes.push_back(entry);
  }

  // Check text content
  if (before.text_content != after.text_content) {
    DiffEntry entry;
    entry.operation = DiffOpType::MODIFIED;
    entry.path = path + "/text()";
    entry.old_value = before.text_content;
    entry.new_value = after.text_content;
    changes.push_back(entry);
  }

  // Check children
  size_t max_children = std::max(before.children.size(), after.children.size());
  for (size_t i = 0; i < max_children; i++) {
    std::string child_path = path + "/[" + std::to_string(i) + "]";

    if (i >= before.children.size()) {
      // Node added
      DiffEntry entry;
      entry.operation = DiffOpType::ADDED;
      entry.path = child_path;
      entry.new_value = after.children[i].tag_name;
      entry.tag_name = after.children[i].tag_name;
      changes.push_back(entry);
    } else if (i >= after.children.size()) {
      // Node removed
      DiffEntry entry;
      entry.operation = DiffOpType::REMOVED;
      entry.path = child_path;
      entry.old_value = before.children[i].tag_name;
      entry.tag_name = before.children[i].tag_name;
      changes.push_back(entry);
    } else {
      // Recurse
      diff_nodes(before.children[i], after.children[i], child_path, changes);
    }
  }
}

DiffResult DOMDiffEngine::diff(const DOMNode &before, const DOMNode &after) {
  DiffResult result;
  result.success = true;
  result.total_nodes_before = count_nodes(before);
  result.total_nodes_after = count_nodes(after);
  result.nodes_added = 0;
  result.nodes_removed = 0;
  result.nodes_modified = 0;

  diff_nodes(before, after, "/", result.changes);

  // Count operations
  for (const auto &change : result.changes) {
    switch (change.operation) {
    case DiffOpType::ADDED:
      result.nodes_added++;
      break;
    case DiffOpType::REMOVED:
      result.nodes_removed++;
      break;
    case DiffOpType::MODIFIED:
      result.nodes_modified++;
      break;
    default:
      break;
    }
  }

  return result;
}

std::string DOMDiffEngine::generate_highlighted_diff(const DiffResult &result) {
  std::ostringstream html;
  html << "<div class=\"dom-diff\">\n";

  for (const auto &change : result.changes) {
    std::string op_class;
    std::string op_name;
    switch (change.operation) {
    case DiffOpType::ADDED:
      op_class = "added";
      op_name = "+";
      break;
    case DiffOpType::REMOVED:
      op_class = "removed";
      op_name = "-";
      break;
    case DiffOpType::MODIFIED:
      op_class = "modified";
      op_name = "~";
      break;
    default:
      continue;
    }

    html << "  <div class=\"diff-entry " << op_class << "\">\n";
    html << "    <span class=\"op\">" << op_name << "</span>\n";
    html << "    <span class=\"path\">" << change.path << "</span>\n";
    if (!change.old_value.empty()) {
      html << "    <span class=\"old\">" << change.old_value << "</span>\n";
    }
    if (!change.new_value.empty()) {
      html << "    <span class=\"new\">" << change.new_value << "</span>\n";
    }
    html << "  </div>\n";
  }

  html << "</div>\n";
  return html.str();
}

// C interface
extern "C" {

void *dom_diff_engine_create() { return new DOMDiffEngine(); }

void dom_diff_engine_destroy(void *engine) {
  delete static_cast<DOMDiffEngine *>(engine);
}

int dom_diff_engine_init(void *engine) {
  if (!engine)
    return -1;
  return static_cast<DOMDiffEngine *>(engine)->initialize() ? 0 : -1;
}

int dom_diff_engine_diff(void *engine, const char *html_before,
                         const char *html_after, char *out_json,
                         int json_buffer_size, int *out_added, int *out_removed,
                         int *out_modified) {
  if (!engine || !html_before || !html_after)
    return -1;

  DOMDiffEngine *diff_engine = static_cast<DOMDiffEngine *>(engine);

  DOMNode before = diff_engine->parse_html(html_before);
  DOMNode after = diff_engine->parse_html(html_after);
  DiffResult result = diff_engine->diff(before, after);

  if (out_json && json_buffer_size > 0) {
    std::string highlighted = diff_engine->generate_highlighted_diff(result);
    strncpy(out_json, highlighted.c_str(), json_buffer_size - 1);
    out_json[json_buffer_size - 1] = '\0';
  }

  if (out_added)
    *out_added = result.nodes_added;
  if (out_removed)
    *out_removed = result.nodes_removed;
  if (out_modified)
    *out_modified = result.nodes_modified;

  return result.success ? 0 : -1;
}

} // extern "C"

} // namespace phase49
