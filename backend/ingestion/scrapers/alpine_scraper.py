"""Alpine Linux SecDB scraper backed by the public JSON feeds."""

from __future__ import annotations

from typing import Any

from backend.ingestion.scrapers.base_scraper import BaseScraper, ScrapedSample


class AlpineSecDBScraper(BaseScraper):
    """Scrape Alpine SecDB package security fixes and normalize them into CVE samples."""

    SOURCE = "alpine"
    REQUEST_DELAY_SECONDS = 1.0
    FEED_URL_TEMPLATE = "https://secdb.alpinelinux.org/{release}/{repo}.json"
    DEFAULT_FEEDS: tuple[tuple[str, str], ...] = (
        ("v3.21", "main"),
        ("v3.21", "community"),
        ("v3.20", "main"),
        ("v3.20", "community"),
        ("edge", "main"),
        ("edge", "community"),
    )

    @staticmethod
    def _normalize_aliases(values: Any) -> tuple[str, ...]:
        if not isinstance(values, list):
            return ()
        aliases: list[str] = []
        for value in values:
            alias = str(value or "").strip().upper()
            if alias.startswith("CVE-") and alias not in aliases:
                aliases.append(alias)
        return tuple(aliases)

    def _iter_secfixes(self, node: Any):
        if isinstance(node, dict):
            secfixes = node.get("secfixes")
            if isinstance(secfixes, dict):
                for fixed_version, aliases in secfixes.items():
                    normalized_aliases = self._normalize_aliases(aliases)
                    if normalized_aliases:
                        yield str(fixed_version or "").strip(), normalized_aliases
            for value in node.values():
                if isinstance(value, (dict, list)):
                    yield from self._iter_secfixes(value)
        elif isinstance(node, list):
            for item in node:
                yield from self._iter_secfixes(item)

    def parse_feed(
        self,
        payload: Any,
        *,
        release: str,
        repo: str,
        max_items: int,
    ) -> list[ScrapedSample]:
        feed_payload = self._ensure_json_object(payload, source=self.SOURCE)
        packages = feed_payload.get("packages", {})
        if not isinstance(packages, dict):
            raise ValueError("alpine: feed payload missing packages map")
        feed_url = self.FEED_URL_TEMPLATE.format(release=release, repo=repo)
        samples: list[ScrapedSample] = []
        seen_keys: set[tuple[str, str]] = set()
        for package_name, package_payload in packages.items():
            normalized_package = str(package_name or "").strip()
            if not normalized_package:
                continue
            for fixed_version, aliases in self._iter_secfixes(package_payload):
                for cve_id in aliases:
                    sample_key = (normalized_package, cve_id)
                    if sample_key in seen_keys:
                        continue
                    seen_keys.add(sample_key)
                    description = (
                        f"Alpine SecDB lists {normalized_package} in {repo} for {release} with a "
                        f"security fix in {fixed_version or 'an updated package release'} for {cve_id}."
                    )
                    samples.append(
                        ScrapedSample(
                            source=self.SOURCE,
                            advisory_id=f"{release}:{repo}:{normalized_package}:{cve_id}",
                            url=feed_url,
                            title=f"{cve_id} in Alpine package {normalized_package}",
                            description=description,
                            severity="UNKNOWN",
                            cve_id=cve_id,
                            tags=(release, repo, normalized_package),
                            aliases=(cve_id,),
                            references=(feed_url,),
                            vendor="Alpine Linux",
                            product=normalized_package,
                        )
                    )
                    if len(samples) >= max_items:
                        return samples
        return samples

    def _fetch_impl(self, max_items: int) -> list[ScrapedSample]:
        samples: list[ScrapedSample] = []
        for release, repo in self.DEFAULT_FEEDS:
            if len(samples) >= max_items:
                break
            feed_url = self.FEED_URL_TEMPLATE.format(release=release, repo=repo)
            try:
                payload = self._get_json(feed_url)
                samples.extend(
                    self.parse_feed(
                        payload,
                        release=release,
                        repo=repo,
                        max_items=max_items - len(samples),
                    )
                )
            except Exception as exc:
                self._log_partial_failure(
                    reason="feed_fetch_failed",
                    release=release,
                    repo=repo,
                    error_type=type(exc).__name__,
                )
        return samples[:max_items]
