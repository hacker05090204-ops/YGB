// asset_discovery.cpp
// Phase-49: Asset Discovery Implementation

#include "asset_discovery.h"
#include <cstring>
#include <sstream>

#ifdef __linux__
#include <arpa/inet.h>
#include <netdb.h>
#include <sys/socket.h>
#include <unistd.h>
#endif

#ifdef _WIN32
#include <winsock2.h>
#include <ws2tcpip.h>
#pragma comment(lib, "ws2_32.lib")
#endif

namespace phase49 {

AssetDiscovery::AssetDiscovery() : initialized_(false) {}

AssetDiscovery::~AssetDiscovery() = default;

bool AssetDiscovery::initialize() {
#ifdef _WIN32
  WSADATA wsaData;
  if (WSAStartup(MAKEWORD(2, 2), &wsaData) != 0) {
    return false;
  }
#endif
  initialized_ = true;
  return true;
}

std::string AssetDiscovery::resolve_ip(const std::string &hostname) {
  struct addrinfo hints, *result;
  memset(&hints, 0, sizeof(hints));
  hints.ai_family = AF_UNSPEC;
  hints.ai_socktype = SOCK_STREAM;

  if (getaddrinfo(hostname.c_str(), nullptr, &hints, &result) != 0) {
    return "";
  }

  char ip[INET6_ADDRSTRLEN];
  void *addr;

  if (result->ai_family == AF_INET) {
    struct sockaddr_in *ipv4 = (struct sockaddr_in *)result->ai_addr;
    addr = &(ipv4->sin_addr);
  } else {
    struct sockaddr_in6 *ipv6 = (struct sockaddr_in6 *)result->ai_addr;
    addr = &(ipv6->sin6_addr);
  }

  inet_ntop(result->ai_family, addr, ip, sizeof(ip));
  freeaddrinfo(result);

  return std::string(ip);
}

std::string AssetDiscovery::grab_banner(const std::string &host, int port,
                                        int timeout_ms) {
  // Create socket
  int sock = socket(AF_INET, SOCK_STREAM, 0);
  if (sock < 0) {
    return "";
  }

  // Set timeout
  struct timeval tv;
  tv.tv_sec = timeout_ms / 1000;
  tv.tv_usec = (timeout_ms % 1000) * 1000;
  setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO, (const char *)&tv, sizeof(tv));
  setsockopt(sock, SOL_SOCKET, SO_SNDTIMEO, (const char *)&tv, sizeof(tv));

  // Resolve host
  struct addrinfo hints, *result;
  memset(&hints, 0, sizeof(hints));
  hints.ai_family = AF_INET;
  hints.ai_socktype = SOCK_STREAM;

  char port_str[16];
  snprintf(port_str, sizeof(port_str), "%d", port);

  if (getaddrinfo(host.c_str(), port_str, &hints, &result) != 0) {
    close(sock);
    return "";
  }

  // Connect
  if (connect(sock, result->ai_addr, result->ai_addrlen) < 0) {
    freeaddrinfo(result);
    close(sock);
    return "";
  }

  freeaddrinfo(result);

  // Read banner
  char buffer[1024];
  ssize_t bytes = recv(sock, buffer, sizeof(buffer) - 1, 0);
  close(sock);

  if (bytes > 0) {
    buffer[bytes] = '\0';
    return std::string(buffer);
  }

  return "";
}

std::vector<int> AssetDiscovery::get_common_ports() const {
  return {21,  22,  23,  25,  53,   80,   110,  143,
          443, 445, 993, 995, 3306, 5432, 8080, 8443};
}

DiscoveryResult AssetDiscovery::discover_subdomains(const std::string &domain,
                                                    bool governance_approved) {
  DiscoveryResult result;
  result.success = false;
  result.total_dns_queries = 0;

  // CRITICAL: Check governance
  if (!governance_approved) {
    result.error_message = "Governance approval required";
    return result;
  }

  // Common subdomain prefixes to check (NO brute force - just common ones)
  std::vector<std::string> prefixes = {"www",  "api",     "app",   "mail",
                                       "smtp", "ftp",     "admin", "blog",
                                       "dev",  "staging", "test"};

  for (const auto &prefix : prefixes) {
    std::string subdomain = prefix + "." + domain;
    std::string ip = resolve_ip(subdomain);
    result.total_dns_queries++;

    if (!ip.empty()) {
      DiscoveredAsset asset;
      asset.type = AssetType::SUBDOMAIN;
      asset.value = subdomain;
      asset.source = "DNS A record";
      asset.parent = domain;
      asset.in_scope = true;
      result.assets.push_back(asset);
    }
  }

  result.success = true;
  return result;
}

DiscoveredAsset AssetDiscovery::fingerprint_service(const std::string &host,
                                                    int port) {
  DiscoveredAsset asset;
  asset.type = AssetType::SERVICE;
  asset.value = host + ":" + std::to_string(port);
  asset.port = port;
  asset.in_scope = true;

  // Try banner grab
  std::string banner = grab_banner(host, port, 2000);

  // Detect service from port or banner
  switch (port) {
  case 21:
    asset.service = "ftp";
    break;
  case 22:
    asset.service = "ssh";
    break;
  case 23:
    asset.service = "telnet";
    break;
  case 25:
    asset.service = "smtp";
    break;
  case 53:
    asset.service = "dns";
    break;
  case 80:
    asset.service = "http";
    break;
  case 110:
    asset.service = "pop3";
    break;
  case 143:
    asset.service = "imap";
    break;
  case 443:
    asset.service = "https";
    break;
  case 3306:
    asset.service = "mysql";
    break;
  case 5432:
    asset.service = "postgresql";
    break;
  default:
    asset.service = "unknown";
  }

  // Extract version from banner
  if (!banner.empty()) {
    // Simple version extraction
    if (banner.find("OpenSSH") != std::string::npos) {
      size_t start = banner.find("OpenSSH");
      size_t end = banner.find(' ', start + 7);
      asset.version = banner.substr(start, end - start);
    } else if (banner.find("nginx") != std::string::npos) {
      size_t start = banner.find("nginx");
      size_t end = banner.find('\r', start);
      if (end == std::string::npos)
        end = banner.find('\n', start);
      asset.version = banner.substr(start, end - start);
    } else if (banner.find("Apache") != std::string::npos) {
      size_t start = banner.find("Apache");
      size_t end = banner.find(' ', start + 6);
      asset.version = banner.substr(start, end - start);
    }
  }

  return asset;
}

std::vector<std::string>
AssetDiscovery::parse_ct_logs(const std::string &json) {
  std::vector<std::string> subdomains;

  // Simple parsing for CT log JSON format
  std::regex domain_regex("\"([a-zA-Z0-9][a-zA-Z0-9.-]+\\.[a-zA-Z]{2,})\"");
  std::sregex_iterator it(json.begin(), json.end(), domain_regex);
  std::sregex_iterator end;

  while (it != end) {
    subdomains.push_back((*it)[1].str());
    ++it;
  }

  return subdomains;
}

// C interface
extern "C" {

void *asset_discovery_create() { return new AssetDiscovery(); }

void asset_discovery_destroy(void *engine) {
  delete static_cast<AssetDiscovery *>(engine);
}

int asset_discovery_init(void *engine) {
  if (!engine)
    return -1;
  return static_cast<AssetDiscovery *>(engine)->initialize() ? 0 : -1;
}

int asset_discovery_subdomains(void *engine, const char *domain,
                               int governance_approved, char *out_json,
                               int json_size) {
  if (!engine || !domain)
    return -1;

  DiscoveryResult result =
      static_cast<AssetDiscovery *>(engine)->discover_subdomains(
          domain, governance_approved != 0);

  if (!result.success) {
    return -1;
  }

  // Build JSON output
  std::ostringstream json;
  json << "{\"subdomains\":[";
  for (size_t i = 0; i < result.assets.size(); i++) {
    json << "\"" << result.assets[i].value << "\"";
    if (i < result.assets.size() - 1)
      json << ",";
  }
  json << "],\"queries\":" << result.total_dns_queries << "}";

  if (out_json && json_size > 0) {
    strncpy(out_json, json.str().c_str(), json_size - 1);
    out_json[json_size - 1] = '\0';
  }

  return static_cast<int>(result.assets.size());
}

int asset_discovery_fingerprint(void *engine, const char *host, int port,
                                char *out_service, int service_size,
                                char *out_version, int version_size) {
  if (!engine || !host)
    return -1;

  DiscoveredAsset asset =
      static_cast<AssetDiscovery *>(engine)->fingerprint_service(host, port);

  if (out_service && service_size > 0) {
    strncpy(out_service, asset.service.c_str(), service_size - 1);
    out_service[service_size - 1] = '\0';
  }
  if (out_version && version_size > 0) {
    strncpy(out_version, asset.version.c_str(), version_size - 1);
    out_version[version_size - 1] = '\0';
  }

  return 0;
}

} // extern "C"

} // namespace phase49
