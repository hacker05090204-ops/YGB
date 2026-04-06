"""Minimal local `pyotp` compatibility layer for the test suite."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import struct
import time
from urllib.parse import quote, urlencode


def random_base32(length: int = 32) -> str:
    raw_length = max(1, (int(length) * 5 + 7) // 8)
    encoded = base64.b32encode(os.urandom(raw_length)).decode("ascii").rstrip("=")
    return encoded[: int(length)]


class TOTP:
    def __init__(self, secret: str, digits: int = 6, interval: int = 30):
        self.secret = str(secret).strip().upper()
        self.digits = int(digits)
        self.interval = int(interval)

    def _decoded_secret(self) -> bytes:
        padding = (-len(self.secret)) % 8
        return base64.b32decode(f"{self.secret}{'=' * padding}", casefold=True)

    def _generate(self, counter: int) -> str:
        key = self._decoded_secret()
        msg = struct.pack(">Q", int(counter))
        digest = hmac.new(key, msg, hashlib.sha1).digest()
        offset = digest[-1] & 0x0F
        code = (struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF) % (10**self.digits)
        return f"{code:0{self.digits}d}"

    def at(self, for_time: int | float) -> str:
        return self._generate(int(float(for_time) // self.interval))

    def now(self) -> str:
        return self.at(time.time())

    def verify(self, otp: str, for_time: int | float | None = None, valid_window: int = 0) -> bool:
        reference_time = time.time() if for_time is None else float(for_time)
        counter = int(reference_time // self.interval)
        candidate = str(otp).strip()
        for offset in range(-int(valid_window), int(valid_window) + 1):
            if hmac.compare_digest(self._generate(counter + offset), candidate):
                return True
        return False

    def provisioning_uri(self, name: str, issuer_name: str | None = None) -> str:
        label = f"{issuer_name}:{name}" if issuer_name else str(name)
        params = {"secret": self.secret}
        if issuer_name:
            params["issuer"] = issuer_name
        return f"otpauth://totp/{quote(label)}?{urlencode(params)}"


__all__ = ["TOTP", "random_base32"]
