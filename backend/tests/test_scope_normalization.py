"""
test_scope_normalization.py — Scope Normalization Hardening

Tests:
- Percent-encoded domains (%2e, %2f)
- Mixed case domains
- Unicode normalization (NFKC)
- Path traversal via encoded separators
- Double-encoding attacks
- Null byte injection
- Tab/newline injection

Requires: 0 bypasses.

NO mock data. NO auto-submit.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))


class ScopeNormalizer:
    """Scope normalizer with hardened input cleaning."""

    @staticmethod
    def normalize(target: str) -> str:
        if not target or not isinstance(target, str):
            return ""

        t = target.strip()

        # Remove protocol
        for proto in ("https://", "http://", "ftp://"):
            if t.lower().startswith(proto):
                t = t[len(proto):]

        # Remove path
        slash = t.find("/")
        if slash != -1:
            t = t[:slash]

        # Remove port
        colon = t.rfind(":")
        if colon > 0:
            after = t[colon + 1:]
            if after.isdigit():
                t = t[:colon]

        # Remove @-sign (userinfo injection)
        at = t.find("@")
        if at != -1:
            t = t[at + 1:]

        # Decode percent-encoding (multi-pass for double encoding)
        for _ in range(3):
            decoded = ScopeNormalizer._percent_decode(t)
            if decoded == t:
                break
            t = decoded

        # Strip null bytes, tabs, newlines
        t = t.replace("\x00", "")
        t = t.replace("\t", "")
        t = t.replace("\n", "")
        t = t.replace("\r", "")

        # Unicode NFKC normalization
        import unicodedata
        t = unicodedata.normalize("NFKC", t)

        # Lowercase
        t = t.lower()

        # Strip trailing dot
        if t.endswith("."):
            t = t[:-1]

        return t

    @staticmethod
    def _percent_decode(s: str) -> str:
        result = []
        i = 0
        while i < len(s):
            if s[i] == "%" and i + 2 < len(s):
                hex_str = s[i + 1:i + 3]
                try:
                    char = chr(int(hex_str, 16))
                    result.append(char)
                    i += 3
                    continue
                except ValueError:
                    pass
            result.append(s[i])
            i += 1
        return "".join(result)

    @staticmethod
    def scope_matches(target: str, pattern: str) -> bool:
        t = ScopeNormalizer.normalize(target)
        p = ScopeNormalizer.normalize(pattern)

        if not t or not p:
            return False

        # Exact match
        if t == p:
            return True

        # Wildcard: *.example.com
        if p.startswith("*."):
            suffix = p[1:]  # .example.com
            base = p[2:]    # example.com

            if t == base:
                return True
            if t.endswith(suffix) and len(t) > len(suffix):
                # Verify the char before suffix is a dot (subdomain boundary)
                prefix = t[:-len(suffix)]
                if prefix and not prefix.endswith("-"):
                    return True

        return False


class ScopeNormalizationTest:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.bypasses = 0
        self.results = []

    def test(self, condition, name, is_bypass_test=False):
        if condition:
            self.passed += 1
            self.results.append(("PASS", name))
        else:
            self.failed += 1
            if is_bypass_test:
                self.bypasses += 1
            self.results.append(("FAIL", name))

    def run_all(self):
        self.test_percent_encoding()
        self.test_mixed_case()
        self.test_unicode_normalization()
        self.test_path_traversal()
        self.test_double_encoding()
        self.test_null_byte_injection()
        self.test_tab_newline_injection()
        self.test_at_sign_injection()
        self.test_trailing_dot()
        self.test_valid_matches()
        self.test_port_stripping()

        print(f"\n  Scope Normalization: {self.passed} passed, "
              f"{self.failed} failed, {self.bypasses} bypasses")
        for status, name in self.results:
            marker = "+" if status == "PASS" else "X"
            print(f"    {marker} {name}")

        # CRITICAL: Zero bypasses required
        if self.bypasses > 0:
            print(f"\n  CRITICAL: {self.bypasses} SCOPE BYPASSES DETECTED")
        return self.failed == 0 and self.bypasses == 0

    def test_percent_encoding(self):
        """Percent-encoded dots and slashes must not bypass scope."""
        n = ScopeNormalizer

        # %2e = .  %2f = /
        self.test(
            not n.scope_matches("evil%2ecom", "*.example.com"),
            "Percent dot: evil%2ecom rejected", True)
        self.test(
            not n.scope_matches("evil.com%2fexample.com", "*.example.com"),
            "Percent slash: path confusion rejected", True)
        self.test(
            n.scope_matches("api%2eexample%2ecom", "*.example.com"),
            "Percent-encoded valid subdomain matches")

    def test_mixed_case(self):
        """Mixed case should normalize to lowercase."""
        n = ScopeNormalizer
        self.test(
            n.scope_matches("API.EXAMPLE.COM", "*.example.com"),
            "All caps matches")
        self.test(
            n.scope_matches("Api.Example.Com", "*.example.com"),
            "Mixed case matches")
        self.test(
            not n.scope_matches("API.EVIL.COM", "*.example.com"),
            "Caps evil domain rejected", True)

    def test_unicode_normalization(self):
        """Unicode homoglyphs and fullwidth chars must not bypass."""
        n = ScopeNormalizer

        # Fullwidth characters (NFKC normalizes these)
        fullwidth_a = "\uff41"  # fullwidth 'a'
        self.test(
            n.normalize(f"{fullwidth_a}pi.example.com") == "api.example.com",
            "Fullwidth 'a' normalized to ASCII")

        # Cyrillic 'a' (U+0430) — not normalized by NFKC
        cyrillic_a = "\u0430"
        normalized = n.normalize(f"ex{cyrillic_a}mple.com")
        self.test(
            not n.scope_matches(f"ex{cyrillic_a}mple.com", "*.example.com"),
            "Cyrillic homoglyph rejected", True)

    def test_path_traversal(self):
        """Path traversal via encoded separators must be blocked."""
        n = ScopeNormalizer
        self.test(
            not n.scope_matches("evil.com/../../example.com",
                                "*.example.com"),
            "Path traversal rejected", True)
        self.test(
            not n.scope_matches("evil.com%2f..%2f..%2fexample.com",
                                "*.example.com"),
            "Encoded path traversal rejected", True)

    def test_double_encoding(self):
        """Double percent-encoding must be decoded and checked."""
        n = ScopeNormalizer
        # %252e = %2e after first decode = . after second
        self.test(
            not n.scope_matches("evil%252ecom", "*.example.com"),
            "Double-encoded dot rejected", True)

    def test_null_byte_injection(self):
        """Null bytes must be stripped — normalization is the defense."""
        n = ScopeNormalizer
        # After null strip: evil.com.example.com -> matches *.example.com
        # This is CORRECT — the null byte is removed, giving a valid subdomain
        self.test(
            n.normalize("evil.com\x00.example.com") == "evil.com.example.com",
            "Null byte stripped from domain", True)
        self.test(
            n.normalize("api\x00.example.com") == "api.example.com",
            "Null byte stripped in normalization")

    def test_tab_newline_injection(self):
        """Tab and newline chars must be stripped."""
        n = ScopeNormalizer
        self.test(
            n.normalize("api\t.example\n.com") == "api.example.com",
            "Tab+newline stripped")
        self.test(
            not n.scope_matches("evil\t.com", "*.example.com"),
            "Tab injection rejected", True)

    def test_at_sign_injection(self):
        """Userinfo @-sign injection — domain after @ is used."""
        n = ScopeNormalizer
        # After normalization: evil.com@example.com -> example.com
        # This correctly extracting the actual domain
        normalized = n.normalize("evil.com@example.com")
        self.test(normalized == "example.com",
                  "@-sign: normalizes to domain after @")
        self.test(
            n.scope_matches("evil.com@example.com", "*.example.com"),
            "@-sign: after strip, base domain matches wildcard")

    def test_trailing_dot(self):
        """Trailing dot must be stripped."""
        n = ScopeNormalizer
        self.test(
            n.normalize("example.com.") == "example.com",
            "Trailing dot stripped")
        self.test(
            n.scope_matches("api.example.com.", "*.example.com"),
            "Trailing dot target still matches")

    def test_valid_matches(self):
        """Verify legitimate matches still work after hardening."""
        n = ScopeNormalizer
        self.test(
            n.scope_matches("api.example.com", "*.example.com"),
            "Standard subdomain matches")
        self.test(
            n.scope_matches("deep.sub.example.com", "*.example.com"),
            "Deep subdomain matches")
        self.test(
            n.scope_matches("example.com", "*.example.com"),
            "Base domain matches wildcard")
        self.test(
            not n.scope_matches("notexample.com", "*.example.com"),
            "Non-matching domain rejected")

    def test_port_stripping(self):
        """Ports must be stripped before matching."""
        n = ScopeNormalizer
        self.test(
            n.scope_matches("api.example.com:8080", "*.example.com"),
            "Port stripped, subdomain matches")
        self.test(
            not n.scope_matches("evil.com:443", "*.example.com"),
            "Port stripped, evil domain rejected", True)


def run_tests():
    test = ScopeNormalizationTest()
    return test.run_all()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
