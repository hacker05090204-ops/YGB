/*
 * HUMANOID_HUNTER Executor Contract
 * 
 * C/C++ Header for Executor Interface
 * 
 * THIS IS A PLACEHOLDER CONTRACT.
 * The actual C/C++ executor will implement this interface.
 */

#ifndef HUMANOID_HUNTER_EXECUTOR_CONTRACT_H
#define HUMANOID_HUNTER_EXECUTOR_CONTRACT_H

#ifdef __cplusplus
extern "C" {
#endif

/**
 * Executor Command Types
 */
typedef enum {
    HH_CMD_NAVIGATE = 1,
    HH_CMD_CLICK = 2,
    HH_CMD_READ = 3,
    HH_CMD_SCROLL = 4,
    HH_CMD_SCREENSHOT = 5,
    HH_CMD_EXTRACT = 6,
    HH_CMD_SHUTDOWN = 7
} HH_CommandType;

/**
 * Executor Response Types
 */
typedef enum {
    HH_RSP_SUCCESS = 1,
    HH_RSP_FAILURE = 2,
    HH_RSP_TIMEOUT = 3,
    HH_RSP_ERROR = 4,
    HH_RSP_REFUSED = 5
} HH_ResponseType;

/**
 * Instruction Envelope
 * 
 * CRITICAL: Executor CANNOT modify instruction_id or execution_id.
 */
typedef struct {
    char instruction_id[64];
    char execution_id[64];
    HH_CommandType command_type;
    char target_url[2048];
    char target_selector[256];
    long timeout_ms;
} HH_InstructionEnvelope;

/**
 * Response Envelope
 * 
 * CRITICAL: SUCCESS requires valid evidence_hash.
 */
typedef struct {
    char instruction_id[64];
    HH_ResponseType response_type;
    char evidence_hash[128];
    char error_message[512];
} HH_ResponseEnvelope;

/**
 * Execute Instruction
 * 
 * CRITICAL: Executor CANNOT decide success.
 *           Executor CANNOT assign evidence authority.
 *           Executor MUST provide evidence_hash for SUCCESS.
 */
int hh_execute_instruction(
    const HH_InstructionEnvelope* instruction,
    HH_ResponseEnvelope* response
);

#ifdef __cplusplus
}
#endif

#endif /* HUMANOID_HUNTER_EXECUTOR_CONTRACT_H */
