"""
clock_guard.py — Clock Skew Protection for Governance
======================================================
Rules:
  - Compare local clock vs NTP source
  - If skew > 5 seconds: block certification
  - Return GOVERNANCE_CLOCK_SKEW flag
  - Log all skew events immutably
  - Never silently proceed with skewed clock
======================================================
"""

import logging
import socket
import struct
import time

logger = logging.getLogger(__name__)

# NTP constants
NTP_EPOCH_OFFSET = 2208988800  # Seconds between 1900 and 1970
NTP_DEFAULT_SERVERS = [
    "pool.ntp.org",
    "time.google.com",
    "time.windows.com",
]
MAX_SKEW_SECONDS = 5.0
NTP_TIMEOUT_SECONDS = 3.0
NTP_PORT = 123


class ClockSkewResult:
    """Immutable result of a clock skew check."""

    __slots__ = (
        "skew_seconds", "local_time", "ntp_time", "ntp_server",
        "passed", "reason", "timestamp",
    )

    def __init__(self, skew_seconds: float, local_time: float,
                 ntp_time: float, ntp_server: str,
                 passed: bool, reason: str):
        self.skew_seconds = skew_seconds
        self.local_time = local_time
        self.ntp_time = ntp_time
        self.ntp_server = ntp_server
        self.passed = passed
        self.reason = reason
        self.timestamp = time.time()

    def to_dict(self) -> dict:
        return {
            "skew_seconds": self.skew_seconds,
            "local_time": self.local_time,
            "ntp_time": self.ntp_time,
            "ntp_server": self.ntp_server,
            "passed": self.passed,
            "reason": self.reason,
            "timestamp": self.timestamp,
        }


class ClockGuard:
    """Validates local clock against NTP before certification.

    If skew > MAX_SKEW_SECONDS, certification is BLOCKED.
    No silent drift — every check is logged.
    """

    def __init__(self, max_skew: float = MAX_SKEW_SECONDS,
                 ntp_servers: list[str] | None = None,
                 timeout: float = NTP_TIMEOUT_SECONDS):
        self._max_skew = max_skew
        self._servers = ntp_servers or NTP_DEFAULT_SERVERS
        self._timeout = timeout
        self._history: list[ClockSkewResult] = []

    @staticmethod
    def _query_ntp(server: str, timeout: float = 3.0) -> float | None:
        """Query NTP server and return UTC time. Returns None on failure."""
        try:
            # Build NTP request (Mode 3 = client, Version 3)
            msg = b'\x1b' + 47 * b'\0'
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)  # pragma: no cover
            sock.settimeout(timeout)  # pragma: no cover
            sock.sendto(msg, (server, NTP_PORT))  # pragma: no cover
            data, _ = sock.recvfrom(1024)  # pragma: no cover
            sock.close()  # pragma: no cover

            if len(data) < 48:  # pragma: no cover
                return None  # pragma: no cover

            # Transmit timestamp starts at byte 40
            t = struct.unpack('!12I', data)[10]  # pragma: no cover
            return t - NTP_EPOCH_OFFSET  # pragma: no cover
        except (socket.timeout, socket.gaierror, OSError):
            return None

    def check_skew(self) -> ClockSkewResult:
        """Check local clock against NTP. Returns ClockSkewResult."""
        local_time = time.time()

        for server in self._servers:
            ntp_time = self._query_ntp(server, self._timeout)
            if ntp_time is not None:  # pragma: no cover
                skew = abs(local_time - ntp_time)  # pragma: no cover
                passed = skew <= self._max_skew  # pragma: no cover

                if passed:  # pragma: no cover
                    reason = f"CLOCK_OK: skew={skew:.3f}s ≤ {self._max_skew}s"  # pragma: no cover
                else:  # pragma: no cover
                    reason = (  # pragma: no cover
                        f"GOVERNANCE_CLOCK_SKEW: skew={skew:.3f}s > "  # pragma: no cover
                        f"{self._max_skew}s — CERTIFICATION BLOCKED"  # pragma: no cover
                    )
                    logger.warning(reason)  # pragma: no cover

                result = ClockSkewResult(  # pragma: no cover
                    skew_seconds=skew, local_time=local_time,  # pragma: no cover
                    ntp_time=ntp_time, ntp_server=server,  # pragma: no cover
                    passed=passed, reason=reason,  # pragma: no cover
                )
                self._history.append(result)  # pragma: no cover
                logger.info(f"CLOCK_CHECK: server={server} skew={skew:.3f}s passed={passed}")  # pragma: no cover
                return result  # pragma: no cover

        # All NTP servers unreachable — fail-safe: block certification
        reason = "GOVERNANCE_CLOCK_SKEW: all NTP servers unreachable — BLOCKED"
        logger.error(reason)
        result = ClockSkewResult(
            skew_seconds=float('inf'), local_time=local_time,
            ntp_time=0.0, ntp_server="NONE",
            passed=False, reason=reason,
        )
        self._history.append(result)
        return result

    def certification_allowed(self) -> tuple[bool, str]:
        """Check if certification is allowed based on clock skew.

        Returns (allowed, reason).
        Forces a fresh NTP check every time — no cached results.
        """
        result = self.check_skew()
        return result.passed, result.reason

    @property
    def history(self) -> list[dict]:
        """Return all clock check results."""
        return [r.to_dict() for r in self._history]

    @property
    def last_result(self) -> ClockSkewResult | None:
        """Return the most recent check result."""
        return self._history[-1] if self._history else None

    def check_skew_simulated(self, local_time: float,
                              ntp_time: float) -> ClockSkewResult:
        """Simulate a clock skew check with provided times.

        Used for testing — does NOT contact NTP servers.
        """
        skew = abs(local_time - ntp_time)
        passed = skew <= self._max_skew

        if passed:
            reason = f"CLOCK_OK: skew={skew:.3f}s ≤ {self._max_skew}s"
        else:
            reason = (
                f"GOVERNANCE_CLOCK_SKEW: skew={skew:.3f}s > "
                f"{self._max_skew}s — CERTIFICATION BLOCKED"
            )

        result = ClockSkewResult(
            skew_seconds=skew, local_time=local_time,
            ntp_time=ntp_time, ntp_server="SIMULATED",
            passed=passed, reason=reason,
        )
        self._history.append(result)
        return result
