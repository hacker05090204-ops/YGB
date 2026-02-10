/**
 * Edge Safe Data Extractor
 * ========================
 * 
 * Extracts structured data from web targets for training.
 * 
 * SECURITY RULES:
 * - Edge MUST NOT train directly
 * - Output to datasets/raw/*.json ONLY
 * - Strip ALL decision fields
 * - No severity, verdicts, or annotations
 * - No dynamic training from live scrape
 * - No browser-to-training connection
 * 
 * FORBIDDEN FIELDS:
 * - valid, accepted, rejected, severity
 * - decision, bounty, platform_verdict
 * - verified, outcome
 */

#include <string>
#include <vector>
#include <map>
#include <fstream>
#include <sstream>
#include <algorithm>
#include <set>
#include <ctime>

/**
 * Forbidden fields that MUST be stripped from all output.
 */
static const std::set<std::string> FORBIDDEN_FIELDS = {
    "valid",
    "accepted",
    "rejected",
    "severity",
    "decision",
    "bounty",
    "platform_verdict",
    "verified",
    "outcome",
    "external_annotation"
};

/**
 * DOM structure element for extraction.
 */
struct DOMElement {
    std::string tag;
    std::map<std::string, std::string> attributes;
    std::vector<DOMElement> children;
    std::string text_content;
};

/**
 * HTTP trace capture result.
 */
struct HTTPTrace {
    std::string method;
    std::string url;
    int status_code;
    std::map<std::string, std::string> request_headers;
    std::map<std::string, std::string> response_headers;
    std::string body_preview;  // First 1024 bytes only
    double response_time_ms;
};

/**
 * Sanitized output record.
 */
struct SanitizedRecord {
    std::string id;
    std::string timestamp;
    std::string source_url;
    std::vector<std::string> dom_tags;
    std::map<std::string, std::string> http_metadata;
    bool is_sanitized;
};


// =============================================================================
// CORE EXTRACTION FUNCTIONS
// =============================================================================

/**
 * Extract DOM structure from HTML content.
 * Returns simplified tag hierarchy for feature extraction.
 * Does NOT execute JavaScript.
 */
DOMElement extract_dom_structure(const std::string& html_content) {
    DOMElement root;
    root.tag = "document";
    
    // Simple tag extraction (no JS execution)
    std::string::size_type pos = 0;
    while (pos < html_content.size()) {
        auto start = html_content.find('<', pos);
        if (start == std::string::npos) break;
        
        auto end = html_content.find('>', start);
        if (end == std::string::npos) break;
        
        std::string tag_content = html_content.substr(start + 1, end - start - 1);
        
        // Skip closing tags and comments
        if (!tag_content.empty() && tag_content[0] != '/' && tag_content[0] != '!') {
            DOMElement child;
            // Extract tag name
            auto space_pos = tag_content.find(' ');
            child.tag = tag_content.substr(0, space_pos);
            // Convert to lowercase
            std::transform(child.tag.begin(), child.tag.end(), child.tag.begin(), ::tolower);
            root.children.push_back(child);
        }
        
        pos = end + 1;
    }
    
    return root;
}

/**
 * Capture HTTP trace from request/response data.
 * Strips body to first 1024 bytes for safety.
 */
HTTPTrace capture_http_trace(
    const std::string& method,
    const std::string& url,
    int status_code,
    const std::map<std::string, std::string>& req_headers,
    const std::map<std::string, std::string>& resp_headers,
    const std::string& body,
    double response_time_ms
) {
    HTTPTrace trace;
    trace.method = method;
    trace.url = url;
    trace.status_code = status_code;
    trace.request_headers = req_headers;
    trace.response_headers = resp_headers;
    trace.response_time_ms = response_time_ms;
    
    // Limit body preview to 1024 bytes
    if (body.size() > 1024) {
        trace.body_preview = body.substr(0, 1024);
    } else {
        trace.body_preview = body;
    }
    
    return trace;
}

/**
 * Normalize HTTP response for feature extraction.
 * Strips sensitive data and forbidden fields.
 */
std::map<std::string, std::string> normalize_response(
    const HTTPTrace& trace
) {
    std::map<std::string, std::string> normalized;
    
    normalized["method"] = trace.method;
    normalized["status_code"] = std::to_string(trace.status_code);
    normalized["response_time_ms"] = std::to_string(trace.response_time_ms);
    normalized["body_length"] = std::to_string(trace.body_preview.size());
    
    // Extract safe headers only
    for (const auto& [key, value] : trace.response_headers) {
        std::string lower_key = key;
        std::transform(lower_key.begin(), lower_key.end(), lower_key.begin(), ::tolower);
        
        // Only include structural headers
        if (lower_key == "content-type" ||
            lower_key == "content-length" ||
            lower_key == "server" ||
            lower_key == "x-frame-options" ||
            lower_key == "content-security-policy" ||
            lower_key == "strict-transport-security") {
            normalized["header_" + lower_key] = value;
        }
    }
    
    return normalized;
}


// =============================================================================
// GOVERNANCE SANITIZATION
// =============================================================================

/**
 * Sanitize output by removing ALL forbidden fields.
 * This is the MANDATORY final step before writing to disk.
 */
SanitizedRecord sanitize_output(
    const std::string& id,
    const std::string& source_url,
    const std::vector<std::string>& dom_tags,
    const std::map<std::string, std::string>& http_metadata
) {
    SanitizedRecord record;
    record.id = id;
    record.source_url = source_url;
    record.dom_tags = dom_tags;
    record.is_sanitized = true;
    
    // Get current timestamp
    time_t now = time(nullptr);
    char buf[64];
    strftime(buf, sizeof(buf), "%Y-%m-%dT%H:%M:%SZ", gmtime(&now));
    record.timestamp = std::string(buf);
    
    // Strip forbidden fields from metadata
    for (const auto& [key, value] : http_metadata) {
        std::string lower_key = key;
        std::transform(lower_key.begin(), lower_key.end(), lower_key.begin(), ::tolower);
        
        if (FORBIDDEN_FIELDS.find(lower_key) == FORBIDDEN_FIELDS.end()) {
            record.http_metadata[key] = value;
        }
        // Silently drop forbidden fields
    }
    
    return record;
}

/**
 * Check if a field name is forbidden.
 */
bool is_forbidden_field(const std::string& field_name) {
    std::string lower = field_name;
    std::transform(lower.begin(), lower.end(), lower.begin(), ::tolower);
    return FORBIDDEN_FIELDS.find(lower) != FORBIDDEN_FIELDS.end();
}

/**
 * Write sanitized record to JSON file in datasets/raw/.
 */
bool write_sanitized_record(
    const SanitizedRecord& record,
    const std::string& output_dir
) {
    if (!record.is_sanitized) {
        return false;  // BLOCK unsanitized output
    }
    
    std::string filepath = output_dir + "/" + record.id + ".json";
    std::ofstream file(filepath);
    
    if (!file.is_open()) {
        return false;
    }
    
    // Write minimal JSON
    file << "{\n";
    file << "  \"id\": \"" << record.id << "\",\n";
    file << "  \"timestamp\": \"" << record.timestamp << "\",\n";
    file << "  \"source_url\": \"" << record.source_url << "\",\n";
    file << "  \"sanitized\": true,\n";
    file << "  \"dom_tags\": [";
    for (size_t i = 0; i < record.dom_tags.size(); i++) {
        if (i > 0) file << ", ";
        file << "\"" << record.dom_tags[i] << "\"";
    }
    file << "],\n";
    file << "  \"http_metadata\": {\n";
    size_t count = 0;
    for (const auto& [key, value] : record.http_metadata) {
        if (count > 0) file << ",\n";
        file << "    \"" << key << "\": \"" << value << "\"";
        count++;
    }
    file << "\n  }\n";
    file << "}\n";
    
    file.close();
    return true;
}
