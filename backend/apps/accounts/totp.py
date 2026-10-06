"""RFC 6238 TOTP (the codes authenticator apps show). ~30 lines; no dependency needed."""

import base64
import hashlib
import hmac
import os
import struct
import time
from urllib.parse import quote

STEP = 30
DIGITS = 6


def generate_secret() -> str:
    return base64.b32encode(os.urandom(20)).decode().rstrip("=")


def _code(secret: str, counter: int) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8))
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10**DIGITS).zfill(DIGITS)


def code_at(secret: str, when: float | None = None) -> str:
    return _code(secret, int((when if when is not None else time.time()) // STEP))


def verify(secret: str, code: str, last_used_step: int, when: float | None = None) -> int | None:
    """Returns the matched step (to store, preventing replay) or None. Accepts ±1 step of clock drift."""
    now_step = int((when if when is not None else time.time()) // STEP)
    for step in (now_step - 1, now_step, now_step + 1):
        if step > last_used_step and hmac.compare_digest(_code(secret, step), (code or "").strip()):
            return step
    return None


def provisioning_uri(secret: str, account: str, issuer: str) -> str:
    return f"otpauth://totp/{quote(issuer)}:{quote(account)}?secret={secret}&issuer={quote(issuer)}&digits={DIGITS}&period={STEP}"
