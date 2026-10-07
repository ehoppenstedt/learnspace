"""Application-level AES-256-GCM encryption for sensitive fields (LFPDPPP).

Ciphertext layout: b"v1:" + key_id + b":" + 12-byte nonce + ciphertext||tag.
The first configured key encrypts; every configured key can decrypt, so keys rotate
by prepending a new one and re-saving rows in a background job.
"""

import base64
import os
from functools import lru_cache

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

_PREFIX = b"v1:"


@lru_cache(maxsize=4)
def _keyring(raw: str) -> tuple[str, dict[str, AESGCM]]:
    keys: dict[str, AESGCM] = {}
    primary = None
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        kid, _, b64 = entry.partition(":")
        key = base64.b64decode(b64)
        if len(key) != 32 or not kid or b":" in kid.encode():
            raise ImproperlyConfigured("FIELD_ENCRYPTION_KEYS entries must be 'kid:<base64 32-byte key>'")
        keys[kid] = AESGCM(key)
        primary = primary or kid
    if primary is None:
        raise ImproperlyConfigured("FIELD_ENCRYPTION_KEYS is empty")
    return primary, keys


def encrypt(plaintext: str, *, context: bytes = b"") -> bytes:
    kid, keys = _keyring(settings.FIELD_ENCRYPTION_KEYS)
    nonce = os.urandom(12)
    ct = keys[kid].encrypt(nonce, plaintext.encode("utf-8"), context or None)
    return _PREFIX + kid.encode() + b":" + nonce + ct


def decrypt(blob: bytes, *, context: bytes = b"") -> str:
    blob = bytes(blob)
    if not blob.startswith(_PREFIX):
        raise ValueError("Unknown ciphertext format")
    kid, _, rest = blob[len(_PREFIX):].partition(b":")
    _, keys = _keyring(settings.FIELD_ENCRYPTION_KEYS)
    aes = keys.get(kid.decode())
    if aes is None:
        raise ValueError(f"No key {kid!r} available to decrypt")
    return aes.decrypt(rest[:12], rest[12:], context or None).decode("utf-8")
