// dom_diff_engine.h
// Phase-49: DOM Tree Diff Engine
//
// STRICT RULES:
// - Read-only DOM parsing
// - No modification of page content
// - Structural diff only

#ifndef PHASE49_DOM_DIFF_ENGINE_H
#define PHASE49_DOM_DIFF_ENGINE_H

#include <string>
#include <vector>

namespace phase49 {

// DOM node type
enum class DOMNodeType { ELEMENT, TEXT, COMMENT, DOCUMENT };

// DOM node structure
struct DOMNode {
  DOMNodeType type;
  std::string tag_name;
  std::string text_content;
  std::string id;
  std::string class_name;
  std::vector<std::pair<std::string, std::string>> attributes;
  std::vector<DOMNode> children;
};

// Diff operation type
enum class DiffOpType { ADDED, REMOVED, MODIFIED, UNCHANGED };

// Diff result entry
struct DiffEntry {
  DiffOpType operation;
  std::string path; // XPath-like path to node
  std::string old_value;
  std::string new_value;
  std::string tag_name;
};

// Diff result
struct DiffResult {
  bool success;
  std::string error_message;
  std::vector<DiffEntry> changes;
  int total_nodes_before;
  int total_nodes_after;
  int nodes_added;
  int nodes_removed;
  int nodes_modified;
};

// DOM Diff Engine
class DOMDiffEngine {
public:
  DOMDiffEngine();
  ~DOMDiffEngine();

  bool initialize();

  // Parse HTML to DOM tree
  DOMNode parse_html(const std::string &html);

  // Calculate diff between two DOM trees
  DiffResult diff(const DOMNode &before, const DOMNode &after);

  // Generate highlighted HTML showing changes
  std::string generate_highlighted_diff(const DiffResult &result);

private:
  bool initialized_;

  // Recursive diff helper
  void diff_nodes(const DOMNode &before, const DOMNode &after,
                  const std::string &path, std::vector<DiffEntry> &changes);

  // Count nodes recursively
  int count_nodes(const DOMNode &node) const;
};

// C interface
extern "C" {
void *dom_diff_engine_create();
void dom_diff_engine_destroy(void *engine);
int dom_diff_engine_init(void *engine);
int dom_diff_engine_diff(void *engine, const char *html_before,
                         const char *html_after, char *out_json,
                         int json_buffer_size, int *out_added, int *out_removed,
                         int *out_modified);
}

} // namespace phase49

#endif // PHASE49_DOM_DIFF_ENGINE_H
