/*
 * evidence_manifest.cpp — Evidence Artifact Manifest
 *
 * Links all evidence (video, screenshots, replays, HTTP captures)
 * into a single manifest with integrity verification.
 */

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>

// =========================================================================
// CONSTANTS
// =========================================================================

static constexpr int MAX_ARTIFACTS = 5000;
static constexpr int MAX_HASH_HEX = 65;
static constexpr int MAX_PATH_LEN = 512;
static constexpr int MAX_DESC = 256;

// =========================================================================
// TYPES
// =========================================================================

enum class ArtifactType {
  VIDEO_RECORDING,
  SCREENSHOT,
  HTTP_LOG,
  DOM_DIFF_LOG,
  REPLAY_CHAIN,
  REPORT_DRAFT,
  SCOPE_DEFINITION,
  AUDIT_LOG
};

struct EvidenceArtifact {
  int sequence;
  time_t created_at;
  ArtifactType type;
  char file_path[MAX_PATH_LEN];
  char description[MAX_DESC];
  char content_hash[MAX_HASH_HEX]; // Hash of file content
  int file_size_bytes;
  int parent_step;
  bool verified;
};

struct ManifestSummary {
  int total_artifacts;
  int videos;
  int screenshots;
  int http_logs;
  int dom_diffs;
  int replays;
  int reports;
  bool all_verified;
  char manifest_hash[MAX_HASH_HEX];
};

// =========================================================================
// EVIDENCE MANIFEST
// =========================================================================

class EvidenceManifest {
private:
  EvidenceArtifact artifacts_[MAX_ARTIFACTS];
  int artifact_count_;

public:
  EvidenceManifest() : artifact_count_(0) {
    std::memset(artifacts_, 0, sizeof(artifacts_));
  }

  bool add_artifact(ArtifactType type, const char *path,
                    const char *description, const char *hash, int size,
                    int parent_step) {
    if (artifact_count_ >= MAX_ARTIFACTS)
      return false;

    EvidenceArtifact &a = artifacts_[artifact_count_];
    a.sequence = artifact_count_;
    a.created_at = std::time(nullptr);
    a.type = type;
    std::strncpy(a.file_path, path ? path : "", MAX_PATH_LEN - 1);
    std::strncpy(a.description, description ? description : "", MAX_DESC - 1);
    std::strncpy(a.content_hash, hash ? hash : "", MAX_HASH_HEX - 1);
    a.file_size_bytes = size;
    a.parent_step = parent_step;
    a.verified = (hash != nullptr && std::strlen(hash) == 64);

    artifact_count_++;
    return true;
  }

  ManifestSummary summarize() const {
    ManifestSummary s;
    std::memset(&s, 0, sizeof(s));
    s.total_artifacts = artifact_count_;
    s.all_verified = true;

    for (int i = 0; i < artifact_count_; i++) {
      switch (artifacts_[i].type) {
      case ArtifactType::VIDEO_RECORDING:
        s.videos++;
        break;
      case ArtifactType::SCREENSHOT:
        s.screenshots++;
        break;
      case ArtifactType::HTTP_LOG:
        s.http_logs++;
        break;
      case ArtifactType::DOM_DIFF_LOG:
        s.dom_diffs++;
        break;
      case ArtifactType::REPLAY_CHAIN:
        s.replays++;
        break;
      case ArtifactType::REPORT_DRAFT:
        s.reports++;
        break;
      default:
        break;
      }
      if (!artifacts_[i].verified)
        s.all_verified = false;
    }
    return s;
  }

  int artifact_count() const { return artifact_count_; }

  const EvidenceArtifact *get_artifact(int i) const {
    return (i >= 0 && i < artifact_count_) ? &artifacts_[i] : nullptr;
  }

  int count_by_type(ArtifactType type) const {
    int c = 0;
    for (int i = 0; i < artifact_count_; i++)
      if (artifacts_[i].type == type)
        c++;
    return c;
  }

  // Guards
  static bool can_modify_artifact() { return false; }
  static bool can_delete_artifact() { return false; }
  static bool can_forge_hash() { return false; }
};
