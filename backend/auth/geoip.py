"""
GeoIP helper for login alerts.

Best-effort lookup with strict timeouts and safe fallbacks.
No hard dependency on external SDKs.
"""

from __future__ import annotations

import ipaddress
import json
import logging
import time
import urllib.request
from typing import Any, Dict, Iterable, Optional

logger = logging.getLogger("ygb.geoip")

_CACHE_TTL_SECONDS = 900
_MAX_CACHE_SIZE = 512
_CACHE: Dict[str, tuple[float, str]] = {}


def _is_private_or_local(ip_address: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_address)
    except ValueError:
        return False
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
    )


def _safe_get(data: Dict[str, Any], keys: Iterable[str]) -> str:
    for key in keys:
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def _format_location(data: Dict[str, Any]) -> str:
    city = _safe_get(data, ("city",))
    region = _safe_get(data, ("region", "regionName"))
    country = _safe_get(data, ("country_name", "country", "countryCode"))

    parts = [p for p in (city, region, country) if p]
    if parts:
        return ", ".join(parts)
    return ""


def _query_provider(url: str, timeout: float = 2.0) -> Optional[Dict[str, Any]]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "YGB-Server"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                return None
            raw = resp.read()
        payload = json.loads(raw.decode("utf-8", errors="replace"))
        if isinstance(payload, dict):
            return payload
    except Exception:
        return None
    return None


def resolve_ip_geolocation(ip_address: str) -> str:
    """
    Resolve geolocation from a public IP.

    Returns a human-readable location string, or a safe fallback.
    """
    ip = (ip_address or "").strip()
    if not ip or ip == "unknown":
        return "Unknown"

    if _is_private_or_local(ip):
        return "Local/Private Network"

    now = time.time()
    cached = _CACHE.get(ip)
    if cached and (now - cached[0]) < _CACHE_TTL_SECONDS:
        return cached[1]

    # Provider order: prefer simple unauthenticated JSON APIs.
    providers = (
        f"https://ipapi.co/{ip}/json/",
        f"https://ipwho.is/{ip}",
    )

    for url in providers:
        payload = _query_provider(url)
        if not payload:
            continue

        # ipwho.is returns {"success": false, ...} on failure
        if payload.get("success") is False:
            continue

        location = _format_location(payload)
        if location:
            if len(_CACHE) >= _MAX_CACHE_SIZE:
                _CACHE.clear()
            _CACHE[ip] = (now, location)
            return location

    logger.warning("GeoIP lookup failed for ip=%s", ip)
    return "Unknown"
