/**
 * device_registry.cpp — Device Registry with 100+ Device Scaling
 *
 * Features:
 *   - Maintains devices.json registry file
 *   - Configurable max_devices limit (default: 100)
 *   - Add device on successful pairing
 *   - Reject pairing if over limit
 *   - Device lookup by ID
 *
 * NO external dependencies.
 */

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <ctime>

namespace device_registry {

// =========================================================================
// CONSTANTS
// =========================================================================

static constexpr char REGISTRY_PATH[] = "config/devices.json";
static constexpr int MAX_DEVICES = 100;
static constexpr int MAX_DEVICE_ID_LEN = 64;

// =========================================================================
// DEVICE ENTRY
// =========================================================================

struct DeviceEntry {
    char device_id[MAX_DEVICE_ID_LEN + 1];
    char device_name[128];
    uint64_t paired_at;     // Unix timestamp
    uint64_t last_seen;     // Unix timestamp
    bool active;
};

// =========================================================================
// IN-MEMORY REGISTRY
// =========================================================================

static DeviceEntry g_devices[MAX_DEVICES];
static int g_device_count = 0;
static int g_max_devices = MAX_DEVICES;

// =========================================================================
// REGISTRY PERSISTENCE
// =========================================================================

static bool save_registry() {
    FILE *f = std::fopen(REGISTRY_PATH, "w");
    if (!f) return false;

    std::fprintf(f, "{\n  \"max_devices\": %d,\n  \"device_count\": %d,\n  \"devices\": [\n",
                 g_max_devices, g_device_count);

    for (int i = 0; i < g_device_count; ++i) {
        const DeviceEntry &d = g_devices[i];
        std::fprintf(f,
            "    {\n"
            "      \"device_id\": \"%s\",\n"
            "      \"device_name\": \"%s\",\n"
            "      \"paired_at\": %llu,\n"
            "      \"last_seen\": %llu,\n"
            "      \"active\": %s\n"
            "    }%s\n",
            d.device_id, d.device_name,
            static_cast<unsigned long long>(d.paired_at),
            static_cast<unsigned long long>(d.last_seen),
            d.active ? "true" : "false",
            (i < g_device_count - 1) ? "," : "");
    }

    std::fprintf(f, "  ]\n}\n");
    std::fclose(f);
    return true;
}

static bool load_registry() {
    FILE *f = std::fopen(REGISTRY_PATH, "r");
    if (!f) {
        // No registry yet — start fresh
        g_device_count = 0;
        return true;
    }

    char buf[65536];
    std::memset(buf, 0, sizeof(buf));
    std::fread(buf, 1, sizeof(buf) - 1, f);
    std::fclose(f);

    // Parse max_devices
    const char *max_pos = std::strstr(buf, "\"max_devices\"");
    if (max_pos) {
        max_pos += 13;
        while (*max_pos && (*max_pos == '"' || *max_pos == ':' || *max_pos == ' ')) ++max_pos;
        std::sscanf(max_pos, "%d", &g_max_devices);
    }

    // Parse device_count
    const char *cnt_pos = std::strstr(buf, "\"device_count\"");
    if (cnt_pos) {
        cnt_pos += 14;
        while (*cnt_pos && (*cnt_pos == '"' || *cnt_pos == ':' || *cnt_pos == ' ')) ++cnt_pos;
        std::sscanf(cnt_pos, "%d", &g_device_count);
    }

    // Parse devices (simplified — scan for device_id entries)
    int idx = 0;
    const char *scan = buf;
    while (idx < g_device_count && idx < MAX_DEVICES) {
        const char *id_pos = std::strstr(scan, "\"device_id\"");
        if (!id_pos) break;
        id_pos += 11;
        while (*id_pos && (*id_pos == '"' || *id_pos == ':' || *id_pos == ' ')) ++id_pos;
        // Read until closing quote
        int j = 0;
        while (*id_pos && *id_pos != '"' && j < MAX_DEVICE_ID_LEN) {
            g_devices[idx].device_id[j++] = *id_pos++;
        }
        g_devices[idx].device_id[j] = '\0';

        // Parse paired_at
        const char *pa_pos = std::strstr(id_pos, "\"paired_at\"");
        if (pa_pos) {
            pa_pos += 11;
            while (*pa_pos && (*pa_pos == '"' || *pa_pos == ':' || *pa_pos == ' ')) ++pa_pos;
            unsigned long long val = 0;
            std::sscanf(pa_pos, "%llu", &val);
            g_devices[idx].paired_at = static_cast<uint64_t>(val);
        }

        g_devices[idx].active = true;
        scan = id_pos;
        ++idx;
    }

    return true;
}

// =========================================================================
// PUBLIC API
// =========================================================================

/**
 * Initialize the device registry.
 * Loads existing registry or creates empty one.
 */
static bool init_registry() {
    return load_registry();
}

/**
 * Check if a device is registered.
 */
static bool is_device_registered(const char *device_id) {
    for (int i = 0; i < g_device_count; ++i) {
        if (std::strcmp(g_devices[i].device_id, device_id) == 0)
            return true;
    }
    return false;
}

/**
 * Register a new device.
 * Returns false if device limit reached or device already registered.
 */
static bool register_device(const char *device_id, const char *device_name) {
    // Check limit
    if (g_device_count >= g_max_devices) {
        std::fprintf(stderr, "[registry] Device limit reached (%d/%d). Rejecting.\n",
                     g_device_count, g_max_devices);
        return false;
    }

    // Check duplicate
    if (is_device_registered(device_id)) {
        std::fprintf(stderr, "[registry] Device %s already registered\n", device_id);
        return false;
    }

    // Add entry
    DeviceEntry &d = g_devices[g_device_count];
    std::memset(&d, 0, sizeof(d));
    std::strncpy(d.device_id, device_id, MAX_DEVICE_ID_LEN);
    std::strncpy(d.device_name, device_name ? device_name : "unknown",
                 sizeof(d.device_name) - 1);
    d.paired_at = static_cast<uint64_t>(std::time(nullptr));
    d.last_seen = d.paired_at;
    d.active = true;

    g_device_count++;

    std::printf("[registry] Registered device %s (%d/%d)\n",
                device_id, g_device_count, g_max_devices);

    return save_registry();
}

/**
 * Update last_seen timestamp for a device.
 */
static bool update_last_seen(const char *device_id) {
    for (int i = 0; i < g_device_count; ++i) {
        if (std::strcmp(g_devices[i].device_id, device_id) == 0) {
            g_devices[i].last_seen = static_cast<uint64_t>(std::time(nullptr));
            return save_registry();
        }
    }
    return false;
}

/**
 * Get current device count and limit.
 */
static void get_capacity(int &count, int &limit) {
    count = g_device_count;
    limit = g_max_devices;
}

} // namespace device_registry

// =========================================================================
// SELF-TEST (compile with -DDEVICE_REGISTRY_MAIN)
// =========================================================================

#ifdef DEVICE_REGISTRY_MAIN
int main() {
    std::printf("=== Device Registry Test ===\n");

    device_registry::init_registry();

    int count, limit;
    device_registry::get_capacity(count, limit);
    std::printf("Current: %d/%d devices\n", count, limit);

    // Register test device
    bool ok = device_registry::register_device("test-device-001", "Test Laptop");
    std::printf("Register: %s\n", ok ? "PASS" : "FAIL (may already exist)");

    // Duplicate should fail
    bool dup = device_registry::register_device("test-device-001", "Duplicate");
    std::printf("Duplicate blocked: %s\n", !dup ? "PASS" : "FAIL");

    // Lookup
    bool found = device_registry::is_device_registered("test-device-001");
    std::printf("Lookup found: %s\n", found ? "PASS" : "FAIL");

    bool not_found = device_registry::is_device_registered("nonexistent");
    std::printf("Lookup not found: %s\n", !not_found ? "PASS" : "FAIL");

    return 0;
}
#endif
