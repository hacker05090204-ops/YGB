/*
 * multi_step_reasoning_graph.cpp — Multi-Step Logic Engine (Phase D)
 *
 * Support:
 *   State transition graphs
 *   Session flow tracking
 *   Privilege shift detection
 *   Multi-request exploit validation
 *
 * C API for Python bridge.
 */

#include <cstdint>
#include <cstring>

#ifdef __cplusplus
extern "C" {
#endif

#define MAX_NODES 128
#define MAX_EDGES 512
#define MAX_SESSIONS 64
#define FIELD_LEN 128
#define HASH_LEN 65

typedef struct {
  int node_id;
  char label[FIELD_LEN];
  int privilege_level; /* 0=none, 1=user, 2=admin, 3=root */
  int data_access;     /* bit flags */
} StateNode;

typedef struct {
  int from_id;
  int to_id;
  char action[FIELD_LEN]; /* HTTP method + path */
  int priv_change;        /* delta in privilege */
} StateEdge;

typedef struct {
  int session_id;
  int steps[MAX_NODES];
  int step_count;
  int start_priv;
  int end_priv;
  int priv_escalation; /* 1 if end > start */
} SessionTrace;

typedef struct {
  int total_nodes;
  int total_edges;
  int total_sessions;
  int escalations;
  int multi_step_exploits;
  double avg_steps;
} GraphReport;

/* Globals */
static StateNode g_nodes[MAX_NODES];
static StateEdge g_edges[MAX_EDGES];
static SessionTrace g_sessions[MAX_SESSIONS];
static int g_node_count = 0;
static int g_edge_count = 0;
static int g_session_count = 0;

/* ---- Public API ---- */

int msrg_init(void) {
  memset(g_nodes, 0, sizeof(g_nodes));
  memset(g_edges, 0, sizeof(g_edges));
  memset(g_sessions, 0, sizeof(g_sessions));
  g_node_count = 0;
  g_edge_count = 0;
  g_session_count = 0;
  return 0;
}

int msrg_add_node(int node_id, const char *label, int priv_level,
                  int data_access) {
  if (g_node_count >= MAX_NODES)
    return -1;
  StateNode *n = &g_nodes[g_node_count];
  n->node_id = node_id;
  strncpy(n->label, label, FIELD_LEN - 1);
  n->privilege_level = priv_level;
  n->data_access = data_access;
  g_node_count++;
  return 0;
}

int msrg_add_edge(int from_id, int to_id, const char *action) {
  if (g_edge_count >= MAX_EDGES)
    return -1;
  StateEdge *e = &g_edges[g_edge_count];
  e->from_id = from_id;
  e->to_id = to_id;
  strncpy(e->action, action, FIELD_LEN - 1);

  /* Find privilege delta */
  int from_priv = 0, to_priv = 0;
  for (int i = 0; i < g_node_count; i++) {
    if (g_nodes[i].node_id == from_id)
      from_priv = g_nodes[i].privilege_level;
    if (g_nodes[i].node_id == to_id)
      to_priv = g_nodes[i].privilege_level;
  }
  e->priv_change = to_priv - from_priv;
  g_edge_count++;
  return 0;
}

int msrg_record_session(int session_id, const int *steps, int step_count) {
  if (g_session_count >= MAX_SESSIONS)
    return -1;
  if (step_count > MAX_NODES)
    step_count = MAX_NODES;

  SessionTrace *s = &g_sessions[g_session_count];
  s->session_id = session_id;
  s->step_count = step_count;
  memcpy(s->steps, steps, step_count * sizeof(int));

  /* Compute privilege escalation */
  if (step_count >= 2) {
    int start = 0, end = 0;
    for (int i = 0; i < g_node_count; i++) {
      if (g_nodes[i].node_id == steps[0])
        start = g_nodes[i].privilege_level;
      if (g_nodes[i].node_id == steps[step_count - 1])
        end = g_nodes[i].privilege_level;
    }
    s->start_priv = start;
    s->end_priv = end;
    s->priv_escalation = (end > start) ? 1 : 0;
  }
  g_session_count++;
  return 0;
}

GraphReport msrg_evaluate(void) {
  GraphReport r;
  memset(&r, 0, sizeof(r));
  r.total_nodes = g_node_count;
  r.total_edges = g_edge_count;
  r.total_sessions = g_session_count;

  int esc = 0, multi = 0;
  double sum_steps = 0;
  for (int i = 0; i < g_session_count; i++) {
    if (g_sessions[i].priv_escalation)
      esc++;
    if (g_sessions[i].step_count >= 3)
      multi++;
    sum_steps += g_sessions[i].step_count;
  }

  r.escalations = esc;
  r.multi_step_exploits = multi;
  r.avg_steps = (g_session_count > 0) ? sum_steps / g_session_count : 0;
  return r;
}

int msrg_get_node_count(void) { return g_node_count; }
int msrg_get_edge_count(void) { return g_edge_count; }
int msrg_get_session_count(void) { return g_session_count; }

#ifdef __cplusplus
}
#endif
