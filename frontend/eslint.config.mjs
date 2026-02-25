/**
 * ESLint flat config for Next.js frontend.
 *
 * Strategy:
 *   1. Try modern flat presets from eslint-config-next@16 (core-web-vitals + typescript).
 *   2. If subpath imports fail, fall back to FlatCompat bridge from @eslint/eslintrc.
 *   3. If both fail, continue with no Next.js rules (ESLint still works for JS/TS basics).
 *
 * This is deterministic and ESM-compatible.
 */

import { globalIgnores } from "eslint/config";
import { fileURLToPath } from "url";
import path from "path";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

let nextConfigs = [];
let configPath = "none";

// --- Path 1: Modern flat presets (eslint-config-next@16+) ---
try {
  const coreWebVitals = await import("eslint-config-next/core-web-vitals");
  const typescript = await import("eslint-config-next/typescript");

  // Each may export a default array or a single config object (CJS compat)
  const normalize = (mod) => {
    const val = mod.default ?? mod;
    return Array.isArray(val) ? val : [val];
  };

  nextConfigs = [...normalize(coreWebVitals), ...normalize(typescript)];
  configPath = "modern-flat";
} catch {
  // --- Path 2: FlatCompat bridge for legacy .eslintrc-style configs ---
  try {
    const { FlatCompat } = await import("@eslint/eslintrc");
    const compat = new FlatCompat({ baseDirectory: __dirname });
    nextConfigs = compat.extends("next/core-web-vitals", "next/typescript");
    configPath = "flatcompat-bridge";
  } catch {
    try {
      const { FlatCompat } = await import("@eslint/eslintrc");
      const compat = new FlatCompat({ baseDirectory: __dirname });
      nextConfigs = compat.extends("next");
      configPath = "flatcompat-base";
    } catch {
      // --- Path 3: No Next.js rules ---
      configPath = "none";
    }
  }
}

// Log which path is active (visible during lint runs)
console.error(`[eslint-config] active path: ${configPath}`);

const eslintConfig = [
  ...nextConfigs,

  // --- Rule overrides (keep rules active as warnings, never disable) ---
  {
    rules: {
      // @typescript-eslint/no-explicit-any: downgrade to warn.
      // Many files use `any` for API responses & interop; warn keeps visibility.
      "@typescript-eslint/no-explicit-any": "warn",
      // react-hooks/purity: experimental rule, downgrade to warn.
      "react-hooks/purity": "warn",
      // react-hooks/set-state-in-render: downgrade to warn.
      // Flags setState calls during render; warn keeps visibility without blocking.
      "react-hooks/set-state-in-render": "warn",
      // react-hooks/set-state-in-effect: downgrade to warn.
      "react-hooks/set-state-in-effect": "warn",
      // react/no-unescaped-entities: downgrade to warn.
      // Prevents build-blocking on quote characters in JSX text.
      "react/no-unescaped-entities": "warn",
      // @next/next/no-html-link-for-pages: downgrade to warn.
      // Keeps guidance active without blocking lint on edge cases.
      "@next/next/no-html-link-for-pages": "warn",
    },
  },

  globalIgnores([
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
  ]),
];

export default eslintConfig;
