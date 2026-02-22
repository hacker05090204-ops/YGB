/**
 * leader_election.cpp — RAFT-like Leader Election (Phase 1)
 *
 * Single-leader guarantee per term.
 * Highest-priority active node wins election.
 * Fencing tokens prevent old leaders from writing state.
 * Strict split-brain prevention.
 *
 * C API for Python ctypes integration.
 */

#include <algorithm>
#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <mutex>
#include <vector>


// ============================================================================
// CONSTANTS
// ============================================================================

#define MAX_NODES 10
#define HEARTBEAT_TIMEOUT 5000 // ms
#define ELECTION_TIMEOUT 3000  // ms

// ============================================================================
// TYPES
// ============================================================================

enum NodeRole {
  ROLE_FOLLOWER = 0,
  ROLE_CANDIDATE = 1,
  ROLE_LEADER = 2,
};

struct NodeState {
  char node_id[64];
  int priority; // Higher = more likely to win
  int term;     // Monotonic term number
  NodeRole role;
  uint64_t fencing_token; // Increments per term
  int voted_for;          // Index of node voted for in this term (-1 = none)
  long last_heartbeat_ms; // Timestamp of last heartbeat received
  int alive;
};

struct ElectionResult {
  int winner_index; // -1 if no winner
  int term;
  uint64_t fencing_token;
  int votes_received;
  int nodes_participated;
  int split_brain; // 1 if split-brain detected
};

// ============================================================================
// GLOBAL STATE
// ============================================================================

static struct {
  NodeState nodes[MAX_NODES];
  int node_count;
  int self_index;
  int current_term;
  uint64_t current_fencing_token;
  int leader_index; // -1 if no leader
  std::mutex mu;
  int initialized;
} g_election = {.node_count = 0,
                .self_index = -1,
                .current_term = 0,
                .current_fencing_token = 0,
                .leader_index = -1,
                .initialized = 0};

static long _now_ms() {
  struct timespec ts;
  timespec_get(&ts, TIME_UTC);
  return (long)(ts.tv_sec * 1000 + ts.tv_nsec / 1000000);
}

// ============================================================================
// C API
// ============================================================================

extern "C" {

/**
 * Initialize the election module.
 *
 * @param self_node_id  This node's ID
 * @param self_priority This node's priority (owner = highest)
 * @return 0 on success
 */
int leader_init(const char *self_node_id, int self_priority) {
  std::lock_guard<std::mutex> lock(g_election.mu);

  memset(g_election.nodes, 0, sizeof(g_election.nodes));
  g_election.node_count = 0;
  g_election.current_term = 0;
  g_election.current_fencing_token = 0;
  g_election.leader_index = -1;

  // Register self as first node
  NodeState &self = g_election.nodes[0];
  strncpy(self.node_id, self_node_id, 63);
  self.priority = self_priority;
  self.term = 0;
  self.role = ROLE_FOLLOWER;
  self.fencing_token = 0;
  self.voted_for = -1;
  self.last_heartbeat_ms = _now_ms();
  self.alive = 1;

  g_election.self_index = 0;
  g_election.node_count = 1;
  g_election.initialized = 1;

  fprintf(stdout, "[ELECTION] Init: id=%s priority=%d\n", self_node_id,
          self_priority);

  return 0;
}

/**
 * Register an additional node for election.
 *
 * @return node index, or -1 if full
 */
int leader_register_node(const char *node_id, int priority) {
  std::lock_guard<std::mutex> lock(g_election.mu);

  if (g_election.node_count >= MAX_NODES) {
    fprintf(stderr, "[ELECTION] Cannot register: max %d nodes\n", MAX_NODES);
    return -1;
  }

  int idx = g_election.node_count;
  NodeState &n = g_election.nodes[idx];
  strncpy(n.node_id, node_id, 63);
  n.priority = priority;
  n.term = g_election.current_term;
  n.role = ROLE_FOLLOWER;
  n.fencing_token = 0;
  n.voted_for = -1;
  n.last_heartbeat_ms = _now_ms();
  n.alive = 1;

  g_election.node_count++;

  fprintf(stdout, "[ELECTION] Registered node %d: id=%s priority=%d\n", idx,
          node_id, priority);

  return idx;
}

/**
 * Run leader election.
 *
 * Algorithm:
 *   1. Increment term
 *   2. Each alive node votes for the highest-priority alive node
 *   3. Node with most votes (and highest priority as tiebreaker) wins
 *   4. Winner gets new fencing token
 *   5. Split-brain check: exactly 1 leader per term
 *
 * @return ElectionResult
 */
ElectionResult leader_run_election(void) {
  std::lock_guard<std::mutex> lock(g_election.mu);

  ElectionResult result;
  memset(&result, 0, sizeof(result));
  result.winner_index = -1;

  int n = g_election.node_count;
  if (n == 0) {
    return result;
  }

  // Step 1: Increment term
  g_election.current_term++;
  int new_term = g_election.current_term;
  result.term = new_term;

  // Step 2: Find highest-priority alive node
  int best_idx = -1;
  int best_priority = -1;
  int alive_count = 0;

  for (int i = 0; i < n; i++) {
    g_election.nodes[i].term = new_term;
    g_election.nodes[i].voted_for = -1;

    if (!g_election.nodes[i].alive)
      continue;
    alive_count++;

    if (g_election.nodes[i].priority > best_priority) {
      best_priority = g_election.nodes[i].priority;
      best_idx = i;
    }
  }

  result.nodes_participated = alive_count;

  if (best_idx < 0 || alive_count == 0) {
    fprintf(stderr, "[ELECTION] No alive nodes — no leader\n");
    return result;
  }

  // Step 3: All alive nodes vote for highest priority
  int votes = 0;
  for (int i = 0; i < n; i++) {
    if (!g_election.nodes[i].alive)
      continue;
    g_election.nodes[i].voted_for = best_idx;
    votes++;
  }

  // Step 4: Verify single winner (split-brain check)
  // In this priority-based model, there is always exactly 1 winner
  // Split-brain would require 2 nodes claiming leader simultaneously
  int leader_count = 0;
  for (int i = 0; i < n; i++) {
    if (g_election.nodes[i].role == ROLE_LEADER) {
      leader_count++;
    }
  }

  // Demote all existing leaders
  for (int i = 0; i < n; i++) {
    g_election.nodes[i].role = ROLE_FOLLOWER;
  }

  // Promote winner
  g_election.nodes[best_idx].role = ROLE_LEADER;

  // Step 5: Assign fencing token
  g_election.current_fencing_token++;
  uint64_t fence = g_election.current_fencing_token;
  g_election.nodes[best_idx].fencing_token = fence;

  g_election.leader_index = best_idx;

  result.winner_index = best_idx;
  result.fencing_token = fence;
  result.votes_received = votes;
  result.split_brain = (leader_count > 1) ? 1 : 0;

  fprintf(stdout,
          "[ELECTION] Term %d: leader=%s (idx=%d, priority=%d) "
          "fence=%llu votes=%d/%d split_brain=%d\n",
          new_term, g_election.nodes[best_idx].node_id, best_idx, best_priority,
          (unsigned long long)fence, votes, alive_count, result.split_brain);

  return result;
}

/**
 * Process a heartbeat from the leader.
 * Resets follower timeout.
 *
 * @param leader_idx  Leader's node index
 * @param fence       Leader's fencing token
 * @return 0 if accepted, -1 if stale (old fencing token)
 */
int leader_heartbeat(int leader_idx, uint64_t fence) {
  std::lock_guard<std::mutex> lock(g_election.mu);

  if (fence < g_election.current_fencing_token) {
    fprintf(stderr,
            "[ELECTION] STALE heartbeat from idx=%d: "
            "fence=%llu < current=%llu\n",
            leader_idx, (unsigned long long)fence,
            (unsigned long long)g_election.current_fencing_token);
    return -1; // Old leader — reject
  }

  long now = _now_ms();
  for (int i = 0; i < g_election.node_count; i++) {
    if (g_election.nodes[i].alive) {
      g_election.nodes[i].last_heartbeat_ms = now;
    }
  }

  return 0;
}

/**
 * Check if leader heartbeat has timed out.
 *
 * @return 1 if timed out (election needed), 0 if OK
 */
int leader_check_timeout(void) {
  std::lock_guard<std::mutex> lock(g_election.mu);

  if (g_election.leader_index < 0)
    return 1;

  long now = _now_ms();
  NodeState &leader = g_election.nodes[g_election.leader_index];
  long elapsed = now - leader.last_heartbeat_ms;

  if (elapsed > HEARTBEAT_TIMEOUT) {
    fprintf(stdout,
            "[ELECTION] Leader timeout: %ldms > %dms — election needed\n",
            elapsed, HEARTBEAT_TIMEOUT);
    leader.alive = 0;
    g_election.leader_index = -1;
    return 1;
  }

  return 0;
}

/**
 * Mark a node as dead/alive.
 */
int leader_set_node_alive(int idx, int alive) {
  std::lock_guard<std::mutex> lock(g_election.mu);

  if (idx < 0 || idx >= g_election.node_count)
    return -1;
  g_election.nodes[idx].alive = alive;

  if (alive) {
    g_election.nodes[idx].last_heartbeat_ms = _now_ms();
  }

  fprintf(stdout, "[ELECTION] Node %d (%s): alive=%d\n", idx,
          g_election.nodes[idx].node_id, alive);

  return 0;
}

/**
 * Validate a fencing token.
 * Returns 0 if valid (current), -1 if stale.
 */
int leader_validate_fence(uint64_t fence) {
  std::lock_guard<std::mutex> lock(g_election.mu);

  if (fence < g_election.current_fencing_token) {
    fprintf(stderr, "[ELECTION] Stale fence: %llu < %llu\n",
            (unsigned long long)fence,
            (unsigned long long)g_election.current_fencing_token);
    return -1;
  }
  return 0;
}

/**
 * Get current election state.
 */
int leader_get_state(int *out_term, int *out_leader_idx, uint64_t *out_fence,
                     int *out_node_count) {
  std::lock_guard<std::mutex> lock(g_election.mu);

  if (out_term)
    *out_term = g_election.current_term;
  if (out_leader_idx)
    *out_leader_idx = g_election.leader_index;
  if (out_fence)
    *out_fence = g_election.current_fencing_token;
  if (out_node_count)
    *out_node_count = g_election.node_count;

  return 0;
}

/**
 * Get a node's info.
 */
int leader_get_node(int idx, char *out_id, int *out_priority, int *out_role,
                    int *out_alive) {
  std::lock_guard<std::mutex> lock(g_election.mu);

  if (idx < 0 || idx >= g_election.node_count)
    return -1;

  NodeState &n = g_election.nodes[idx];
  if (out_id)
    strncpy(out_id, n.node_id, 63);
  if (out_priority)
    *out_priority = n.priority;
  if (out_role)
    *out_role = (int)n.role;
  if (out_alive)
    *out_alive = n.alive;

  return 0;
}

} // extern "C"
