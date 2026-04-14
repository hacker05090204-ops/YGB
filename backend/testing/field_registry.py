from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from typing import Any, Sequence

# Mirror of the expert ordering used by the Phase 49 MoE stack.
# Kept local here so the Phase 6 CLI stays lightweight and does not depend on
# optional training/runtime packages.
EXPERT_FIELDS: tuple[str, ...] = (
    "web_vulns",
    "api_testing",
    "mobile_apk",
    "cloud_misconfig",
    "blockchain",
    "iot",
    "hardware",
    "firmware",
    "ssrf",
    "rce",
    "xss",
    "sqli",
    "auth_bypass",
    "idor",
    "graphql_abuse",
    "rest_attacks",
    "csrf",
    "file_upload",
    "deserialization",
    "privilege_escalation",
    "cryptography",
    "subdomain_takeover",
    "race_condition",
)

EXPERT_INDEX: dict[str, int] = {
    expert_name: expert_id for expert_id, expert_name in enumerate(EXPERT_FIELDS)
}
SEVERITY_ORDER: tuple[str, ...] = ("critical", "high", "medium", "low")
_VALID_SEVERITIES = set(SEVERITY_ORDER)


def _spec(
    slug: str,
    title: str,
    description: str,
    severity: str,
    expert_name: str,
    *test_patterns: str,
) -> dict[str, Any]:
    return {
        "slug": slug,
        "title": title,
        "description": description,
        "severity": severity,
        "expert_name": expert_name,
        "test_patterns": tuple(test_patterns),
    }


_CATEGORY_SPECS: tuple[tuple[str, tuple[dict[str, Any], ...]], ...] = (
    (
        "client_side",
        (
            _spec(
                "dom_xss_reflected",
                "DOM XSS reflected sink",
                "Untrusted browser-controlled data reaches dangerous DOM sinks without sanitization.",
                "high",
                "xss",
                "innerHTML",
                "location.hash",
                "document.write",
            ),
            _spec(
                "stored_xss_widget",
                "Stored XSS in reusable widget",
                "Persistent markup injection executes when shared widgets, comments, or previews are rendered.",
                "critical",
                "xss",
                "comment preview",
                "rich text editor",
                "stored payload replay",
            ),
            _spec(
                "client_template_injection",
                "Client-side template injection",
                "Client templating features render attacker-controlled expressions or trusted HTML fragments.",
                "high",
                "web_vulns",
                "triple braces",
                "v-html",
                "template expression execution",
            ),
            _spec(
                "csrf_token_bypass",
                "CSRF token validation bypass",
                "State-changing browser requests succeed when token binding or origin verification can be bypassed.",
                "high",
                "csrf",
                "missing csrf token",
                "state-changing GET",
                "same-site lax exception",
            ),
            _spec(
                "clickjacking_ui_redress",
                "Clickjacking and UI redress",
                "Sensitive actions remain frameable or visually overlaid in a way that coerces unintended clicks.",
                "medium",
                "web_vulns",
                "X-Frame-Options absent",
                "frame-ancestors wildcard",
                "hidden overlay",
            ),
            _spec(
                "open_redirect_chain",
                "Open redirect chaining",
                "Navigation endpoints allow controlled redirect targets that can be chained into phishing or token theft.",
                "medium",
                "web_vulns",
                "redirect_uri",
                "continue=",
                "next=",
            ),
            _spec(
                "postmessage_origin_trust",
                "postMessage origin trust failure",
                "Cross-window messaging accepts attacker-controlled origins or wildcard trust boundaries.",
                "high",
                "web_vulns",
                "window.postMessage",
                "origin == *",
                "message event trust",
            ),
        ),
    ),
    (
        "api_business_logic",
        (
            _spec(
                "graphql_introspection_leak",
                "GraphQL introspection leak",
                "GraphQL schema discovery remains enabled in production and reveals privileged attack surface.",
                "medium",
                "graphql_abuse",
                "__schema",
                "introspection enabled",
                "graphiql exposed",
            ),
            _spec(
                "graphql_batching_bypass",
                "GraphQL batching bypass",
                "Batching and alias abuse evade intended request cost or authorization limits.",
                "high",
                "graphql_abuse",
                "batched queries",
                "alias fan-out",
                "depth limit bypass",
            ),
            _spec(
                "rest_rate_limit_bypass",
                "REST rate-limit bypass",
                "API throttling can be bypassed through header spoofing, token spray, or route fan-out.",
                "high",
                "rest_attacks",
                "X-Forwarded-For rotation",
                "endpoint fan-out",
                "token spray",
            ),
            _spec(
                "business_logic_price_tampering",
                "Business logic price tampering",
                "Server-side purchase validation trusts client-provided pricing, quantity, or discount state.",
                "critical",
                "api_testing",
                "negative quantity",
                "client-side price",
                "coupon stacking",
            ),
            _spec(
                "webhook_signature_bypass",
                "Webhook signature bypass",
                "Inbound webhook handling accepts forged events because integrity checks can be skipped or confused.",
                "high",
                "api_testing",
                "missing HMAC validation",
                "algorithm confusion",
                "unsigned webhook",
            ),
            _spec(
                "mass_assignment_override",
                "Mass assignment override",
                "Hidden or privileged object properties can be overwritten through unrestricted API binding.",
                "high",
                "rest_attacks",
                "is_admin",
                "role field",
                "hidden JSON property",
            ),
            _spec(
                "api_version_shadow_route",
                "Shadow API version route",
                "Legacy or undocumented API versions expose weaker validation and stale business rules.",
                "medium",
                "api_testing",
                "/v1/legacy",
                "undocumented endpoint",
                "stale OpenAPI",
            ),
        ),
    ),
    (
        "mobile_security",
        (
            _spec(
                "android_exported_activity",
                "Android exported activity abuse",
                "Exported components can be invoked externally to access privileged application flows.",
                "high",
                "mobile_apk",
                "exported=true",
                "deep link abuse",
                "implicit intent",
            ),
            _spec(
                "insecure_webview_bridge",
                "Insecure WebView bridge",
                "Mobile WebView bridges expose privileged native actions to untrusted content.",
                "high",
                "mobile_apk",
                "addJavascriptInterface",
                "file:// access",
                "mixed content",
            ),
            _spec(
                "mobile_certificate_pinning_bypass",
                "Mobile certificate pinning bypass",
                "Transport trust accepts user-controlled roots, debug trust managers, or disabled pin checks.",
                "high",
                "mobile_apk",
                "trust manager override",
                "debug pin set",
                "user CA accepted",
            ),
            _spec(
                "local_storage_token_leak",
                "Local storage token leak",
                "Bearer tokens or session secrets are persisted insecurely on the device.",
                "medium",
                "mobile_apk",
                "shared prefs token",
                "sqlite cache",
                "world-readable file",
            ),
            _spec(
                "biometric_fallback_abuse",
                "Biometric fallback abuse",
                "Fallback flows after biometric failure downgrade to weaker or replayable device credentials.",
                "high",
                "auth_bypass",
                "device credential fallback",
                "weak fallback PIN",
                "insecure prompt reuse",
            ),
            _spec(
                "mobile_deeplink_auth_bypass",
                "Mobile deep link auth bypass",
                "Custom schemes or app links permit attacker-controlled login completion or callback interception.",
                "critical",
                "auth_bypass",
                "app link wildcard",
                "auth callback spoofing",
                "custom scheme hijack",
            ),
            _spec(
                "exposed_debug_component",
                "Exposed debug component",
                "Debug-only activities, menus, or hidden administration surfaces remain reachable in production builds.",
                "medium",
                "mobile_apk",
                "debuggable flag",
                "test activity",
                "hidden admin screen",
            ),
        ),
    ),
    (
        "cloud_security",
        (
            _spec(
                "public_object_storage",
                "Public object storage exposure",
                "Object storage permissions permit public listing or download of sensitive assets.",
                "critical",
                "cloud_misconfig",
                "public-read bucket",
                "anonymous listing",
                "signed URL overexposure",
            ),
            _spec(
                "iam_privilege_chain",
                "IAM privilege chaining",
                "Cloud role configuration permits chained escalation through overly broad identity permissions.",
                "critical",
                "privilege_escalation",
                "passRole",
                "wildcard action",
                "assume role chain",
            ),
            _spec(
                "metadata_ssrf_pivot",
                "Metadata SSRF pivot",
                "Server-side fetch behavior can reach cloud instance metadata or internal credential endpoints.",
                "critical",
                "ssrf",
                "169.254.169.254",
                "IMDSv1",
                "metadata proxy",
            ),
            _spec(
                "container_escape_surface",
                "Container escape surface",
                "Container runtime or orchestration settings expose host-level escape primitives.",
                "high",
                "privilege_escalation",
                "privileged container",
                "hostPID",
                "docker socket mount",
            ),
            _spec(
                "exposed_control_plane_api",
                "Exposed control-plane API",
                "Administrative cloud, cluster, or orchestration APIs are reachable without intended network restrictions.",
                "high",
                "cloud_misconfig",
                "kubelet anonymous auth",
                "dashboard open",
                "etcd exposed",
            ),
            _spec(
                "ci_cd_secret_sprawl",
                "CI/CD secret sprawl",
                "Build and deployment systems leak secrets through logs, artifacts, or poorly scoped environment variables.",
                "high",
                "cloud_misconfig",
                "plaintext secret variable",
                "build log secret",
                "artifact credential leak",
            ),
            _spec(
                "serverless_event_injection",
                "Serverless event injection",
                "Event-driven compute trusts unvalidated messages, queue payloads, or replayed execution context.",
                "high",
                "api_testing",
                "unsanitized event payload",
                "queue replay",
                "step function trust",
            ),
        ),
    ),
    (
        "identity_access",
        (
            _spec(
                "idor_account_takeover",
                "IDOR-driven account takeover",
                "Predictable object references expose direct access to another user's sensitive account actions.",
                "critical",
                "idor",
                "predictable user_id",
                "sequential object key",
                "missing owner check",
            ),
            _spec(
                "sso_relaystate_abuse",
                "SSO relay state abuse",
                "Single sign-on flows trust attacker-controlled relay or redirect state without adequate validation.",
                "high",
                "auth_bypass",
                "unsigned relaystate",
                "ACS mismatch",
                "IdP initiated flow abuse",
            ),
            _spec(
                "password_reset_poisoning",
                "Password reset poisoning",
                "Reset links or reset recipients are influenced by attacker-controlled request metadata.",
                "critical",
                "auth_bypass",
                "host header poisoning",
                "poisoned reset link",
                "email parameter override",
            ),
            _spec(
                "oauth_scope_escalation",
                "OAuth scope escalation",
                "OAuth clients or authorization servers grant more capability than intended after parameter tampering.",
                "high",
                "privilege_escalation",
                "scope parameter tampering",
                "incremental auth abuse",
                "stale consent",
            ),
            _spec(
                "session_fixation_reuse",
                "Session fixation and reuse",
                "Session identifiers are not rotated safely across privilege boundaries or login state transitions.",
                "high",
                "auth_bypass",
                "pre-auth session token",
                "no rotation on login",
                "remember me reuse",
            ),
            _spec(
                "tenant_boundary_break",
                "Tenant boundary break",
                "Multi-tenant authorization trusts client-controlled identifiers or stale tenancy routing metadata.",
                "critical",
                "idor",
                "tenant_id tampering",
                "org switch header",
                "cross-tenant record access",
            ),
            _spec(
                "role_cache_invalidation_gap",
                "Role cache invalidation gap",
                "Access revocation lags behind cached role or permission state long enough to be exploitable.",
                "medium",
                "privilege_escalation",
                "stale RBAC cache",
                "JWT role drift",
                "delayed permission revoke",
            ),
        ),
    ),
    (
        "injection",
        (
            _spec(
                "sql_injection_blind",
                "Blind SQL injection",
                "Database queries incorporate attacker input in a way that supports boolean or time-based exfiltration.",
                "critical",
                "sqli",
                "sleep()",
                "boolean condition",
                "ORDER BY probe",
            ),
            _spec(
                "nosql_operator_injection",
                "NoSQL operator injection",
                "Untrusted structured input is interpreted as query operators rather than literal values.",
                "high",
                "sqli",
                "$ne",
                "$where",
                "regex operator",
            ),
            _spec(
                "command_injection_pipeline",
                "Command injection in processing pipeline",
                "Application workflows concatenate attacker-controlled input into shell commands or subprocess invocations.",
                "critical",
                "rce",
                "shell metacharacters",
                "command chaining",
                "environment expansion",
            ),
            _spec(
                "server_template_injection",
                "Server-side template injection",
                "Server-side rendering accepts templates or expressions that execute arbitrary logic.",
                "critical",
                "rce",
                "{{7*7}}",
                "template error leak",
                "sandbox escape",
            ),
            _spec(
                "ldap_xpath_injection",
                "LDAP and XPath injection",
                "Directory and XML query construction embeds untrusted expressions without proper encoding.",
                "medium",
                "web_vulns",
                "*)(uid=*",
                "//user[1]",
                "filter concatenation",
            ),
            _spec(
                "insecure_deserialization_rce",
                "Insecure deserialization RCE",
                "Serialized attacker input is materialized into executable object graphs or gadget chains.",
                "critical",
                "deserialization",
                "pickle loads",
                "readObject",
                "gadget chain",
            ),
            _spec(
                "expression_language_injection",
                "Expression language injection",
                "Dynamic expression features allow arbitrary evaluation in server-side business logic.",
                "high",
                "rce",
                "${}",
                "SpEL",
                "OGNL",
            ),
        ),
    ),
    (
        "file_data",
        (
            _spec(
                "unrestricted_file_upload",
                "Unrestricted file upload",
                "Upload validation permits attacker-controlled executable or polyglot files to reach dangerous storage or execution paths.",
                "critical",
                "file_upload",
                "extension bypass",
                "MIME confusion",
                "polyglot file",
            ),
            _spec(
                "archive_traversal_zip_slip",
                "Archive traversal (Zip Slip)",
                "Archive extraction logic writes attacker-chosen paths outside the intended destination root.",
                "high",
                "file_upload",
                "../ in zip",
                "tar symlink",
                "extraction root escape",
            ),
            _spec(
                "xml_external_entity",
                "XML external entity processing",
                "XML parsing supports external entity resolution and local or remote resource access.",
                "high",
                "web_vulns",
                "<!DOCTYPE",
                "SYSTEM identifier",
                "file:///etc/passwd",
            ),
            _spec(
                "csv_formula_injection",
                "CSV formula injection",
                "Exported spreadsheets contain attacker input that executes spreadsheet formulas on open.",
                "medium",
                "file_upload",
                "=cmd|",
                "+SUM",
                "spreadsheet export",
            ),
            _spec(
                "image_parser_memory_corruption",
                "Image parser memory corruption surface",
                "Media handling routes malformed images into native decoders with crash or corruption potential.",
                "high",
                "file_upload",
                "malformed EXIF",
                "image magic mismatch",
                "decoder crash",
            ),
            _spec(
                "backup_export_data_leak",
                "Backup export data leak",
                "Automated export or backup files are disclosed without adequate authorization or secrecy controls.",
                "medium",
                "web_vulns",
                "/backup.zip",
                "export endpoint",
                "unsigned download",
            ),
            _spec(
                "schema_poisoning_import",
                "Schema poisoning during import",
                "Structured imports load attacker-controlled schemas, plugins, or YAML into dangerous runtime paths.",
                "high",
                "deserialization",
                "unsafe YAML load",
                "schema plugin execution",
                "import hook",
            ),
        ),
    ),
    (
        "cryptography",
        (
            _spec(
                "jwt_alg_confusion",
                "JWT algorithm confusion",
                "JWT verification accepts unsafe algorithms or attacker-controlled key interpretation paths.",
                "critical",
                "cryptography",
                "alg=none",
                "RSA/HMAC swap",
                "kid injection",
            ),
            _spec(
                "weak_password_hashing",
                "Weak password hashing",
                "Credential storage relies on outdated or under-configured password hashing mechanisms.",
                "high",
                "cryptography",
                "md5",
                "unsalted sha1",
                "low bcrypt cost",
            ),
            _spec(
                "insecure_random_token",
                "Insecure random token generation",
                "Security tokens derive from predictable, low-entropy, or attacker-influenced randomness.",
                "high",
                "cryptography",
                "predictable seed",
                "Math.random",
                "time-based token",
            ),
            _spec(
                "key_rotation_gap",
                "Key rotation gap",
                "Cryptographic key management fails to retire stale keys or bind issued artifacts to key versions.",
                "medium",
                "cryptography",
                "stale signing key",
                "no key version",
                "revoked key reuse",
            ),
            _spec(
                "padding_oracle_surface",
                "Padding oracle surface",
                "Distinct decryption behaviors expose padding oracle attacks against encrypted content.",
                "high",
                "cryptography",
                "distinct decrypt errors",
                "CBC padding",
                "byte-by-byte oracle",
            ),
            _spec(
                "hardcoded_secret_material",
                "Hardcoded secret material",
                "Static credentials, private keys, or shared secrets are embedded in source, builds, or mobile artifacts.",
                "medium",
                "cryptography",
                "API_KEY=",
                "private key in repo",
                "mobile secret constant",
            ),
            _spec(
                "signature_verification_bypass",
                "Signature verification bypass",
                "Signed artifacts are trusted without strict signature verification or trusted chain enforcement.",
                "critical",
                "cryptography",
                "missing verify()",
                "trust untrusted cert",
                "detached signature ignored",
            ),
        ),
    ),
    (
        "blockchain_security",
        (
            _spec(
                "smart_contract_reentrancy",
                "Smart contract reentrancy",
                "External calls occur before critical state updates and allow repeated draining of contract state.",
                "critical",
                "blockchain",
                "external call before state update",
                "fallback loop",
                "withdraw reentry",
            ),
            _spec(
                "oracle_manipulation_window",
                "Oracle manipulation window",
                "On-chain pricing depends on manipulable or stale external value feeds.",
                "high",
                "blockchain",
                "low liquidity pair",
                "TWAP gap",
                "stale oracle round",
            ),
            _spec(
                "access_control_modifier_gap",
                "Modifier-based access control gap",
                "Critical smart contract functions lack proper owner, role, or initializer protection.",
                "critical",
                "blockchain",
                "onlyOwner missing",
                "initializer open",
                "role check omission",
            ),
            _spec(
                "bridge_replay_attack",
                "Bridge replay attack",
                "Cross-chain verification allows replayed proofs, messages, or nonces to execute more than once.",
                "critical",
                "blockchain",
                "nonce reuse",
                "chain id missing",
                "duplicate proof",
            ),
            _spec(
                "unsafe_delegatecall_usage",
                "Unsafe delegatecall usage",
                "Delegatecall patterns trust attacker-controlled destinations or storage layouts.",
                "high",
                "blockchain",
                "delegatecall to user input",
                "library address swap",
                "storage collision",
            ),
            _spec(
                "tx_origin_authentication",
                "tx.origin authentication misuse",
                "Authorization decisions rely on tx.origin instead of resilient caller context.",
                "high",
                "blockchain",
                "tx.origin",
                "phishing contract",
                "proxy auth confusion",
            ),
            _spec(
                "integer_rounding_drain",
                "Integer rounding drain",
                "Fixed-point arithmetic or rounding gaps leak funds or value over repeated transactions.",
                "medium",
                "blockchain",
                "precision loss",
                "floor division",
                "fee dust drain",
            ),
        ),
    ),
    (
        "iot_firmware",
        (
            _spec(
                "default_device_credentials",
                "Default device credentials",
                "Fielded devices retain vendor-default administrative access methods.",
                "critical",
                "iot",
                "admin/admin",
                "telnet enabled",
                "default password reuse",
            ),
            _spec(
                "unsigned_firmware_update",
                "Unsigned firmware update",
                "Firmware update flows accept unauthenticated or downgradeable images.",
                "critical",
                "firmware",
                "no signature check",
                "update over HTTP",
                "rollback accepted",
            ),
            _spec(
                "uart_console_exposure",
                "UART console exposure",
                "Accessible hardware debug interfaces expose boot interaction or shell access.",
                "high",
                "hardware",
                "exposed headers",
                "boot log shell",
                "serial unlock",
            ),
            _spec(
                "insecure_ble_pairing",
                "Insecure BLE pairing",
                "Bluetooth pairing and bonding rely on weak association or static secrets.",
                "medium",
                "iot",
                "Just Works pairing",
                "no MITM",
                "static passkey",
            ),
            _spec(
                "ota_manifest_tampering",
                "OTA manifest tampering",
                "Update manifests and update metadata can be altered without being rejected.",
                "high",
                "firmware",
                "update manifest unsigned",
                "hash mismatch ignored",
                "version rollback",
            ),
            _spec(
                "sensor_trust_spoofing",
                "Sensor trust spoofing",
                "Hardware or field calibration trust can be spoofed to mislead downstream device decisions.",
                "medium",
                "hardware",
                "spoofed GPIO",
                "fake sensor feed",
                "calibration bypass",
            ),
            _spec(
                "fieldbus_command_injection",
                "Fieldbus command injection",
                "Industrial or embedded control buses accept unauthorized write or spoofed control frames.",
                "high",
                "iot",
                "Modbus write abuse",
                "CAN frame spoofing",
                "unauthenticated command",
            ),
        ),
    ),
    (
        "infrastructure",
        (
            _spec(
                "subdomain_takeover_dangling_dns",
                "Subdomain takeover via dangling DNS",
                "Dangling DNS or unclaimed third-party hosting lets attackers claim trusted subdomains.",
                "high",
                "subdomain_takeover",
                "dangling CNAME",
                "unclaimed SaaS",
                "NXDOMAIN proof",
            ),
            _spec(
                "dns_zone_transfer_leak",
                "DNS zone transfer leak",
                "Authoritative DNS configuration exposes internal naming data through unrestricted AXFR.",
                "medium",
                "subdomain_takeover",
                "AXFR allowed",
                "misconfigured NS",
                "host inventory leak",
            ),
            _spec(
                "internal_proxy_ssrf",
                "Internal proxy SSRF",
                "Fetch helpers, redirect chains, or protocol smuggling route requests into internal services.",
                "critical",
                "ssrf",
                "gopher payload",
                "protocol smuggling",
                "internal redirect abuse",
            ),
            _spec(
                "origin_service_exposure",
                "Origin service exposure",
                "Backend origin services remain reachable directly outside the intended CDN or edge controls.",
                "high",
                "cloud_misconfig",
                "bypass CDN",
                "origin IP leaked",
                "direct host access",
            ),
            _spec(
                "mail_domain_spoofing",
                "Mail domain spoofing",
                "Mail infrastructure policy gaps allow spoofed mail to inherit trusted domain identity.",
                "medium",
                "web_vulns",
                "SPF softfail",
                "DMARC none",
                "subdomain mail host",
            ),
            _spec(
                "edge_cache_poisoning",
                "Edge cache poisoning",
                "Shared caches accept attacker-controlled variants that poison later victim responses.",
                "high",
                "rest_attacks",
                "header normalization",
                "unkeyed query param",
                "vary confusion",
            ),
            _spec(
                "exposed_admin_interface",
                "Exposed administrative interface",
                "Management panels, consoles, or ports are reachable without intended network isolation.",
                "high",
                "cloud_misconfig",
                "default admin path",
                "VPN bypass",
                "management port open",
            ),
        ),
    ),
    (
        "concurrency_integrity",
        (
            _spec(
                "coupon_race_double_spend",
                "Coupon race double spend",
                "Parallel redemption flows permit the same discount or credit to be consumed more than once.",
                "high",
                "race_condition",
                "parallel redemption",
                "no row lock",
                "stale balance",
            ),
            _spec(
                "inventory_reservation_bypass",
                "Inventory reservation bypass",
                "Concurrent ordering paths oversell or bypass intended reservation guarantees.",
                "high",
                "race_condition",
                "check-then-act",
                "concurrent checkout",
                "oversell",
            ),
            _spec(
                "webhook_replay_idempotency_gap",
                "Webhook replay idempotency gap",
                "Asynchronous event processing accepts duplicate deliveries without resilient replay protection.",
                "medium",
                "rest_attacks",
                "missing idempotency key",
                "event replay",
                "duplicate charge",
            ),
            _spec(
                "job_queue_claim_collision",
                "Job queue claim collision",
                "Distributed workers claim the same work item because queue ownership is not enforced atomically.",
                "medium",
                "race_condition",
                "non-atomic claim",
                "duplicate worker execution",
                "stale lock",
            ),
            _spec(
                "privilege_cache_race",
                "Privilege cache race",
                "Authorization caches and delayed state propagation create a window for stale privileges.",
                "high",
                "privilege_escalation",
                "async revoke delay",
                "stale session privilege",
                "eventual consistency",
            ),
            _spec(
                "payment_state_desync",
                "Payment state desynchronization",
                "Async payment flows accept inconsistent callback ordering or double-settlement conditions.",
                "critical",
                "race_condition",
                "async callback order",
                "double capture",
                "partial refund mismatch",
            ),
            _spec(
                "distributed_lock_bypass",
                "Distributed lock bypass",
                "Cluster coordination relies on weak lock expiry or missing fencing semantics.",
                "high",
                "race_condition",
                "Redis lock expiry",
                "clock skew",
                "missing fencing token",
            ),
        ),
    ),
)


def _labelize(identifier: str) -> str:
    return identifier.replace("_", " ").title()


def _copy_field(field: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": field["id"],
        "slug": field["slug"],
        "title": field["title"],
        "category": field["category"],
        "description": field["description"],
        "severity": field["severity"],
        "expert_id": field["expert_id"],
        "expert_name": field["expert_name"],
        "test_patterns": tuple(field["test_patterns"]),
    }


def _build_registry() -> tuple[dict[str, Any], ...]:
    registry: list[dict[str, Any]] = []
    seen_slugs: set[str] = set()

    for category, fields in _CATEGORY_SPECS:
        for spec in fields:
            slug = str(spec["slug"])
            if slug in seen_slugs:
                raise ValueError(f"Duplicate field slug detected: {slug}")

            severity = str(spec["severity"]).strip().lower()
            if severity not in _VALID_SEVERITIES:
                raise ValueError(f"Invalid severity for {slug}: {severity}")

            expert_name = str(spec["expert_name"]).strip()
            if expert_name not in EXPERT_INDEX:
                raise KeyError(f"Unknown expert mapping for {slug}: {expert_name}")

            test_patterns = tuple(str(pattern) for pattern in spec["test_patterns"])
            if not test_patterns:
                raise ValueError(f"Field {slug} must define at least one test pattern")

            registry.append(
                {
                    "id": len(registry),
                    "slug": slug,
                    "title": str(spec["title"]),
                    "category": category,
                    "description": str(spec["description"]),
                    "severity": severity,
                    "expert_id": EXPERT_INDEX[expert_name],
                    "expert_name": expert_name,
                    "test_patterns": test_patterns,
                }
            )
            seen_slugs.add(slug)

    if len(registry) < 80:
        raise ValueError(f"Phase 6 requires at least 80 fields, found {len(registry)}")

    return tuple(registry)


FIELD_REGISTRY: tuple[dict[str, Any], ...] = _build_registry()
TOTAL_FIELDS: int = len(FIELD_REGISTRY)
FIELD_BY_ID: dict[int, dict[str, Any]] = {field["id"]: field for field in FIELD_REGISTRY}
FIELD_BY_SLUG: dict[str, dict[str, Any]] = {field["slug"]: field for field in FIELD_REGISTRY}

_fields_by_expert: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
_fields_by_category: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
for _field in FIELD_REGISTRY:
    _fields_by_expert[_field["expert_name"]].append(_field)
    _fields_by_category[_field["category"]].append(_field)

FIELDS_BY_EXPERT: dict[str, tuple[dict[str, Any], ...]] = {
    expert_name: tuple(fields)
    for expert_name, fields in sorted(_fields_by_expert.items(), key=lambda item: EXPERT_INDEX[item[0]])
}
FIELDS_BY_CATEGORY: dict[str, tuple[dict[str, Any], ...]] = {
    category: tuple(fields) for category, fields in sorted(_fields_by_category.items())
}


def list_fields() -> tuple[dict[str, Any], ...]:
    return tuple(_copy_field(field) for field in FIELD_REGISTRY)


def get_field_by_id(field_id: int | str) -> dict[str, Any]:
    try:
        normalized_id = int(field_id)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"field_id must be an integer-like value, got {field_id!r}") from exc

    if normalized_id not in FIELD_BY_ID:
        raise KeyError(f"Unknown field_id={normalized_id}")
    return _copy_field(FIELD_BY_ID[normalized_id])


def get_field_by_slug(slug: str) -> dict[str, Any]:
    normalized_slug = str(slug or "").strip()
    if not normalized_slug:
        raise ValueError("slug is required")
    if normalized_slug not in FIELD_BY_SLUG:
        raise KeyError(f"Unknown field slug: {normalized_slug}")
    return _copy_field(FIELD_BY_SLUG[normalized_slug])


def _resolve_expert(expert: int | str) -> tuple[int, str]:
    if isinstance(expert, int):
        if expert < 0 or expert >= len(EXPERT_FIELDS):
            raise KeyError(f"Unknown expert_id={expert}")
        return expert, EXPERT_FIELDS[expert]

    expert_text = str(expert or "").strip()
    if not expert_text:
        raise ValueError("expert is required")
    if expert_text.isdigit():
        return _resolve_expert(int(expert_text))
    if expert_text not in EXPERT_INDEX:
        raise KeyError(f"Unknown expert name: {expert_text}")
    return EXPERT_INDEX[expert_text], expert_text


def get_fields_for_expert(expert: int | str) -> tuple[dict[str, Any], ...]:
    _, expert_name = _resolve_expert(expert)
    return tuple(_copy_field(field) for field in FIELDS_BY_EXPERT.get(expert_name, ()))


def get_fields_for_category(category: str) -> tuple[dict[str, Any], ...]:
    category_name = str(category or "").strip()
    if not category_name:
        raise ValueError("category is required")
    return tuple(_copy_field(field) for field in FIELDS_BY_CATEGORY.get(category_name, ()))


def get_category_distribution() -> dict[str, int]:
    counter = Counter(field["category"] for field in FIELD_REGISTRY)
    return {category: counter[category] for category in sorted(counter)}


def get_severity_distribution() -> dict[str, int]:
    counter = Counter(field["severity"] for field in FIELD_REGISTRY)
    return {severity: counter[severity] for severity in SEVERITY_ORDER if counter.get(severity, 0)}


def build_summary() -> dict[str, Any]:
    return {
        "total_fields": TOTAL_FIELDS,
        "experts_total": len(EXPERT_FIELDS),
        "experts_covered": len({field["expert_name"] for field in FIELD_REGISTRY}),
        "category_distribution": get_category_distribution(),
        "severity_distribution": get_severity_distribution(),
    }


def render_report() -> str:
    summary = build_summary()
    lines = [
        "Phase 6 Field Registry Report",
        "============================",
        f"Total fields: {summary['total_fields']}",
        f"Experts covered: {summary['experts_covered']} / {summary['experts_total']}",
        "Category distribution:",
    ]

    for category, count in summary["category_distribution"].items():
        lines.append(f"- {_labelize(category)}: {count}")

    lines.append("Severity distribution:")
    for severity, count in summary["severity_distribution"].items():
        lines.append(f"- {severity.title()}: {count}")
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Phase 6 static vulnerability field registry")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of the text report")
    parser.add_argument("--field-id", type=int, help="Look up a single field by numeric id")
    parser.add_argument("--field-slug", help="Look up a single field by slug")
    parser.add_argument("--expert", help="List fields assigned to an expert id or expert name")
    parser.add_argument("--category", help="List fields assigned to a category")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.field_id is not None:
        payload: Any = get_field_by_id(args.field_id)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    if args.field_slug:
        payload = get_field_by_slug(args.field_slug)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    if args.expert:
        payload = get_fields_for_expert(args.expert)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    if args.category:
        payload = get_fields_for_category(args.category)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    if args.json:
        print(json.dumps(build_summary(), indent=2, sort_keys=True))
        return 0

    print(render_report())
    return 0


__all__ = [
    "EXPERT_FIELDS",
    "EXPERT_INDEX",
    "FIELD_REGISTRY",
    "TOTAL_FIELDS",
    "FIELD_BY_ID",
    "FIELD_BY_SLUG",
    "FIELDS_BY_EXPERT",
    "FIELDS_BY_CATEGORY",
    "list_fields",
    "get_field_by_id",
    "get_field_by_slug",
    "get_fields_for_expert",
    "get_fields_for_category",
    "get_category_distribution",
    "get_severity_distribution",
    "build_summary",
    "render_report",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
