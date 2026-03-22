# IMPL_V1 Phase-36 Audit Report

## Scope

Phase-36 restores the missing governance link for the Native Sandbox Boundary.
This phase is interface-only and contains no execution logic or side effects
outside import-time SHA-256 logging.

## Files

| File | Purpose | SHA-256 |
| --- | --- | --- |
| `impl_v1/phase36/phase36_types.py` | Closed enums for boundary type, capability, decision | `C0ADE35C443F9DB867FAA69F6CCCFA5709DF2CA974C9E35540DE23DB9DE61420` |
| `impl_v1/phase36/phase36_context.py` | Frozen interface/result dataclasses | `898E1916EF3551F6C2F8B36CC19D8EBE4491EBEF46A39092BF9B1BDD5C3A24E9` |
| `impl_v1/phase36/phase36_engine.py` | Pure deny-by-default evaluation engine | `5C0D47A8E6FF1CAC40EF31F2DB7E2A978AD051E8BA45A7265A41C4261E1CF80A` |
| `impl_v1/phase36/__init__.py` | Public exports | `EFC0579F629F5DE56EEE80A17690AC40C9CB4E76DB4840EEA9B29C16624E36A9` |
| `impl_v1/phase36/tests/test_phase36_types.py` | Closed-enum verification | `F78C332E827A032E8895042812A220838F1E90F53950463D0E3C63ED83ACF355` |
| `impl_v1/phase36/tests/test_phase36_context.py` | Frozen dataclass verification | `201E837C32E040F89E6E04E8EFCB0A31323DF5C62C6692247F2D8485DB668242` |
| `impl_v1/phase36/tests/test_phase36_engine.py` | Deny/escalate/default engine verification | `987D0E974DAD71E42216DA2C91554560647D82BC512F2397861EB4915A30485C` |
| `impl_v1/phase36/tests/test_forbidden_imports.py` | Forbidden import scan | `331B7E657CC990D33466C0215834C746406006726ECDD91A95B4BED3058E618D` |
| `impl_v1/phase36/tests/__init__.py` | Test package marker | `3076F57EAD84161B75398DC10E80AA3D833E4E13C86027E7D85D1D3BC5624D97` |

## Evaluation Rules

The Phase-36 engine applies these rules in order:

1. Empty `boundary_id` -> `DENY`
2. `UNKNOWN` boundary type -> `DENY`
3. `EXEC_ALLOWED` capability -> `ESCALATE`
4. `threat_level > 7` -> `DENY`
5. `WRITE_ALLOWED` with `threat_level > 4` -> `ESCALATE`
6. No declared capabilities -> `DENY`
7. Default -> `DENY`

## Verification

- `pytest impl_v1/phase36/tests` -> `4 passed`
- Coverage target for the Phase-36 package was satisfied during focused verification
- Forbidden import scan confirmed no `subprocess`, `os.system`, `requests`, `phase37`, or `phase48` references in the implementation set
