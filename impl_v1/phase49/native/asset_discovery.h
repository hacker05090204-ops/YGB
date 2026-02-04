// asset_discovery.h
// Phase-49: Asset Discovery Engine
//
// STRICT RULES:
// - NO brute force
// - Safe DNS queries only
// - Passive fingerprinting

#ifndef PHASE49_ASSET_DISCOVERY_H
#define PHASE49_ASSET_DISCOVERY_H

#include <string>
#include <vector>

namespace phase49 {

// Asset type
enum class AssetType { DOMAIN, SUBDOMAIN, IP_ADDRESS, SERVICE, TECHNOLOGY };

// Discovered asset
struct DiscoveredAsset {
  AssetType type;
  std::string value;
  std::string source;  // How it was discovered
  std::string parent;  // Parent domain if subdomain
  int port;            // For services
  std::string service; // Service name (http, https, ssh, etc.)
  std::string version; // Detected version
  bool in_scope;
};

// Discovery result
struct DiscoveryResult {
  bool success;
  std::string error_message;
  std::vector<DiscoveredAsset> assets;
  int total_dns_queries;
};

// Asset discovery engine
class AssetDiscovery {
public:
  AssetDiscovery();
  ~AssetDiscovery();

  bool initialize();

  // Discover subdomains from DNS
  DiscoveryResult discover_subdomains(const std::string &domain,
                                      bool governance_approved);

  // Fingerprint service on host:port
  DiscoveredAsset fingerprint_service(const std::string &host, int port);

  // Parse subdomains from certificate transparency logs
  std::vector<std::string> parse_ct_logs(const std::string &json);

  // Get common ports to check
  std::vector<int> get_common_ports() const;

private:
  bool initialized_;

  // DNS resolution (uses getaddrinfo)
  std::string resolve_ip(const std::string &hostname);

  // Banner grab for fingerprinting
  std::string grab_banner(const std::string &host, int port, int timeout_ms);
};

// C interface
extern "C" {
void *asset_discovery_create();
void asset_discovery_destroy(void *engine);
int asset_discovery_init(void *engine);
int asset_discovery_subdomains(void *engine, const char *domain,
                               int governance_approved, char *out_json,
                               int json_size);
int asset_discovery_fingerprint(void *engine, const char *host, int port,
                                char *out_service, int service_size,
                                char *out_version, int version_size);
}

} // namespace phase49

#endif // PHASE49_ASSET_DISCOVERY_H
