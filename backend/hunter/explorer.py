"""Autonomous web explorer.
Discovers: pages, endpoints, parameters, forms, API routes,
JavaScript files, hidden paths, tech stack.
No external tools — pure HTTP + regex + HTML parsing."""

import asyncio
import hashlib
import logging
import re
import urllib.parse
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Set

logger = logging.getLogger("ygb.hunter.explorer")


@dataclass
class Endpoint:
    url: str
    method: str = "GET"
    params: list[str] = field(default_factory=list)
    headers: dict = field(default_factory=dict)
    content_type: str = ""
    response_status: int = 0
    tech_stack: list[str] = field(default_factory=list)
    interesting_score: float = 0.0  # 0-1, higher = more worth testing
    notes: list[str] = field(default_factory=list)


@dataclass
class ExplorationResult:
    target: str
    endpoints: list[Endpoint]
    tech_stack: list[str]
    interesting_params: dict[str, list[str]]  # param → endpoints that have it
    forms: list[dict]
    api_routes: list[str]
    js_files: list[str]
    secrets_found: list[dict]  # API keys, tokens in JS
    subdomains_discovered: list[str]
    total_pages_visited: int
    exploration_time_s: float


class TechFingerprinter:
    """Identifies technologies from headers + body."""

    SIGNATURES = {
        "nginx": [("server", "nginx")],
        "apache": [("server", "apache")],
        "iis": [("server", "iis")],
        "cloudflare": [("server", "cloudflare"), ("cf-ray", None)],
        "aws": [("x-amz-", None), ("x-amzn-", None)],
        "django": [("x-frame-options", "sameorigin"), ("csrfmiddlewaretoken", None)],
        "rails": [("x-request-id", None), ("_rails_session", None)],
        "laravel": [("laravel_session", None), ("x-ratelimit-limit", None)],
        "express": [("x-powered-by", "express")],
        "php": [("x-powered-by", "php"), ("phpsessid", None)],
        "wordpress": [("wp-content", None), ("wp-json", None)],
        "react": [("__next", None), ("_reactrouter", None)],
        "graphql": [("graphql", None), ("introspection", None)],
        "jwt": [("authorization", "bearer"), ("eyj", None)],
    }

    BODY_SIGNATURES = {
        "wordpress": ["wp-content/plugins", "wp-includes", "wordpress"],
        "django": ["csrfmiddlewaretoken", "django"],
        "graphql": ["__typename", "__schema", "graphql"],
        "react": ["react-root", "__react", "reactdom"],
        "angular": ["ng-app", "ng-controller", "angular"],
        "vue": ["v-bind", "v-model", "__vue__"],
        "spring": ["org.springframework", "spring-boot"],
        "struts": ["struts", ".action"],
    }

    def identify(self, headers: dict, body: str, cookies: dict) -> list[str]:
        found = set()
        headers_lower = {k.lower(): v.lower() for k, v in headers.items()}
        body_lower = body.lower()

        for tech, sigs in self.SIGNATURES.items():
            for header_key, header_val in sigs:
                if header_val is None:
                    if any(header_key in k for k in headers_lower):
                        found.add(tech)
                else:
                    if header_key in headers_lower and header_val in headers_lower[header_key]:
                        found.add(tech)

            if tech in cookies or any(tech in k.lower() for k in cookies):
                found.add(tech)

        for tech, patterns in self.BODY_SIGNATURES.items():
            if any(p in body_lower for p in patterns):
                found.add(tech)

        return sorted(found)


class HTMLParser:
    """Lightweight HTML parser — no BeautifulSoup dependency."""

    def extract_links(self, html: str, base_url: str) -> list[str]:
        links = []
        # Find all href and src
        for match in re.finditer(
            r'(?:href|src|action)=["\']([^"\'<>]+)["\']', html, re.IGNORECASE
        ):
            href = match.group(1).strip()
            if href and not href.startswith(("javascript:", "mailto:", "tel:", "#")):
                full = urllib.parse.urljoin(base_url, href)
                links.append(full)
        return links

    def extract_forms(self, html: str, base_url: str) -> list[dict]:
        forms = []
        for form_match in re.finditer(
            r"<form[^>]*>(.*?)</form>", html, re.DOTALL | re.IGNORECASE
        ):
            form_html = form_match.group(0)
            action = re.search(r'action=["\']([^"\']+)["\']', form_html, re.IGNORECASE)
            method = re.search(r'method=["\']([^"\']+)["\']', form_html, re.IGNORECASE)
            inputs = re.findall(
                r'<input[^>]+name=["\']([^"\']+)["\']', form_html, re.IGNORECASE
            )
            textareas = re.findall(
                r'<textarea[^>]+name=["\']([^"\']+)["\']', form_html, re.IGNORECASE
            )

            forms.append(
                {
                    "action": urllib.parse.urljoin(base_url, action.group(1))
                    if action
                    else base_url,
                    "method": (method.group(1).upper() if method else "GET"),
                    "inputs": inputs + textareas,
                }
            )
        return forms

    def extract_js_vars(self, html: str) -> dict:
        """Find API endpoints and tokens in JavaScript."""
        found = {}

        # API endpoints in JS
        api_patterns = re.findall(
            r'["\']/(api|v\d|graphql|rest|admin)[/\w-]+["\']', html, re.IGNORECASE
        )
        if api_patterns:
            found["api_endpoints"] = list(set(api_patterns))

        # Potential secrets
        secret_patterns = [
            (r'["\']([A-Za-z0-9+/]{32,}={0,2})["\']', "base64_token"),
            (r'api[_-]?key["\s]*[:=]["\s]*["\']([^"\']{16,})["\']', "api_key"),
            (r'token["\s]*[:=]["\s]*["\']([^"\']{16,})["\']', "token"),
            (r'secret["\s]*[:=]["\s]*["\']([^"\']{16,})["\']', "secret"),
            (r'password["\s]*[:=]["\s]*["\']([^"\']{4,})["\']', "password"),
        ]

        for pattern, label in secret_patterns:
            matches = re.findall(pattern, html, re.IGNORECASE)
            if matches:
                found[label] = [
                    m[:50] + "..." if len(m) > 50 else m for m in matches[:5]
                ]

        return found

    def extract_params_from_url(self, url: str) -> list[str]:
        parsed = urllib.parse.urlparse(url)
        return list(urllib.parse.parse_qs(parsed.query).keys())


class AutonomousExplorer:
    """Crawls a target autonomously.
    Discovers all endpoints, parameters, forms, tech stack.
    Stays within scope. Respects rate limits."""

    MAX_PAGES = 150
    MAX_DEPTH = 4

    INTERESTING_PATHS = [
        "/api",
        "/v1",
        "/v2",
        "/graphql",
        "/admin",
        "/login",
        "/register",
        "/search",
        "/user",
        "/account",
        "/profile",
        "/upload",
        "/download",
        "/export",
        "/import",
        "/webhook",
        "/callback",
        "/oauth",
        "/token",
        "/password",
        "/reset",
        "/verify",
        "/confirm",
        "/settings",
        "/config",
        "/.env",
        "/.git/config",
        "/robots.txt",
        "/sitemap.xml",
        "/api/docs",
        "/swagger.json",
        "/openapi.json",
        "/api-docs",
    ]

    COMMON_PARAMS = [
        "id",
        "user_id",
        "user",
        "username",
        "file",
        "path",
        "url",
        "redirect",
        "callback",
        "next",
        "return",
        "q",
        "search",
        "query",
        "page",
        "limit",
        "offset",
        "sort",
        "order",
        "filter",
        "token",
        "key",
        "api_key",
        "session",
        "lang",
        "format",
    ]

    def __init__(self, http: "SmartHTTPEngine", scope: "ScopeValidator"):
        self._http = http
        self._scope = scope
        self._fingerprinter = TechFingerprinter()
        self._html_parser = HTMLParser()
        self._visited: Set[str] = set()
        self._endpoints: list[Endpoint] = []

    def _normalize_url(self, url: str) -> str:
        parsed = urllib.parse.urlparse(url)
        # Remove fragments
        return urllib.parse.urlunparse(
            (parsed.scheme, parsed.netloc, parsed.path, parsed.params, parsed.query, "")
        )

    def _url_key(self, url: str) -> str:
        """Deduplicate URLs with different param values but same structure."""
        parsed = urllib.parse.urlparse(url)
        params = urllib.parse.parse_qs(parsed.query)
        param_keys = sorted(params.keys())
        return f"{parsed.netloc}{parsed.path}?{'&'.join(param_keys)}"

    def _score_endpoint(self, endpoint: Endpoint) -> float:
        score = 0.0
        url_lower = endpoint.url.lower()

        # High-value endpoints
        for kw in [
            "/admin",
            "/api/",
            "/graphql",
            "/upload",
            "/delete",
            "/execute",
            "/run",
            "/eval",
            "/query",
            "/export",
        ]:
            if kw in url_lower:
                score += 0.2

        # Parameters increase attack surface
        score += min(0.3, len(endpoint.params) * 0.05)

        # POST is more interesting
        if endpoint.method == "POST":
            score += 0.15

        # Server errors reveal info
        if endpoint.response_status in (500, 501, 502, 503):
            score += 0.25

        return min(1.0, score)

    async def explore(
        self, target: str, scope_rules: list[str], max_pages: int = MAX_PAGES
    ) -> ExplorationResult:
        import time

        t_start = time.perf_counter()

        # Verify scope
        domain = urllib.parse.urlparse(target).netloc
        scope_check = self._scope.validate(domain, scope_rules)
        if not scope_check.in_scope:
            raise ValueError(f"Target {target} is NOT in scope: {scope_rules}")

        logger.info("Starting exploration: %s (max %d pages)", target, max_pages)

        queue = deque([(target, 0)])
        all_tech = set()
        all_forms = []
        js_files = []
        secrets = []
        api_routes = []
        interesting_params: dict[str, list] = {}

        # Check known interesting paths first
        for path in self.INTERESTING_PATHS:
            url = urllib.parse.urljoin(target, path)
            if self._url_key(url) not in self._visited:
                queue.appendleft((url, 1))  # high priority

        while queue and len(self._visited) < max_pages:
            url, depth = queue.popleft()
            url = self._normalize_url(url)
            key = self._url_key(url)

            if key in self._visited or depth > self.MAX_DEPTH:
                continue

            # Scope check
            endpoint_domain = urllib.parse.urlparse(url).netloc
            if not self._scope.validate(endpoint_domain, scope_rules).in_scope:
                continue

            self._visited.add(key)

            try:
                from backend.hunter.http_engine import HTTPRequest

                resp = await self._http.send(HTTPRequest("GET", url, timeout=10.0))
            except Exception as e:
                logger.debug("Explorer failed: %s → %s", url, e)
                continue

            # Fingerprint tech
            tech = self._fingerprinter.identify(resp.headers, resp.body, resp.cookies)
            all_tech.update(tech)

            # Parse links
            if resp.is_html:
                links = self._html_parser.extract_links(resp.body, url)
                forms = self._html_parser.extract_forms(resp.body, url)
                all_forms.extend(forms)

                for link in links:
                    link_domain = urllib.parse.urlparse(link).netloc
                    if self._scope.validate(link_domain, scope_rules).in_scope:
                        queue.append((link, depth + 1))

                # Extract JS variables and secrets
                js_vars = self._html_parser.extract_js_vars(resp.body)
                if js_vars.get("api_key") or js_vars.get("token") or js_vars.get("secret"):
                    secrets.append({"url": url, "found": js_vars})

                if js_vars.get("api_endpoints"):
                    api_routes.extend(js_vars["api_endpoints"])

            # Detect JS files
            if url.endswith(".js") or "javascript" in resp.content_type:
                js_files.append(url)
                js_vars = self._html_parser.extract_js_vars(resp.body)
                if any(
                    js_vars.get(k) for k in ("api_key", "token", "secret", "password")
                ):
                    secrets.append({"url": url, "found": js_vars})

            # Extract params
            url_params = self._html_parser.extract_params_from_url(url)
            for p in url_params:
                interesting_params.setdefault(p, []).append(url)

            # Build endpoint
            endpoint = Endpoint(
                url=url,
                method="GET",
                params=url_params,
                content_type=resp.content_type,
                response_status=resp.status_code,
                tech_stack=tech,
            )
            endpoint.interesting_score = self._score_endpoint(endpoint)

            if resp.has_error_message:
                endpoint.notes.append("server_error_detected")

            self._endpoints.append(endpoint)

        # Add form endpoints
        for form in all_forms:
            endpoint = Endpoint(
                url=form["action"],
                method=form["method"],
                params=form["inputs"],
            )
            endpoint.interesting_score = self._score_endpoint(endpoint)
            if form["inputs"]:
                endpoint.notes.append(f"form_inputs: {form['inputs']}")
            self._endpoints.append(endpoint)

        # Sort endpoints by interest
        self._endpoints.sort(key=lambda e: e.interesting_score, reverse=True)

        elapsed = time.perf_counter() - t_start
        logger.info(
            "Exploration complete: %d pages, %d endpoints, %.1fs",
            len(self._visited),
            len(self._endpoints),
            elapsed,
        )

        return ExplorationResult(
            target=target,
            endpoints=self._endpoints[:200],  # top 200
            tech_stack=sorted(all_tech),
            interesting_params=interesting_params,
            forms=all_forms,
            api_routes=list(set(api_routes)),
            js_files=list(set(js_files)),
            secrets_found=secrets,
            subdomains_discovered=[],
            total_pages_visited=len(self._visited),
            exploration_time_s=round(elapsed, 2),
        )
