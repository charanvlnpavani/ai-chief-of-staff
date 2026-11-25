"""Application-level encryption (AES-256-GCM) with key rotation.

Blob layout: version (1 byte) | key-id length (1) | key id | nonce (12) | ciphertext+tag.
The key id travels with each blob, so old blobs stay readable after you add a new key
at the front of ENCRYPTION_KEYS. `aad` binds a blob to its row (e.g. a conversation id),
so ciphertext copied into another row fails to decrypt.
"""

import base64
import binascii
import os
from functools import lru_cache

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import get_settings

_VERSION = 1


class Keyring:
    def __init__(self, spec: str) -> None:
        self._keys: dict[str, bytes] = {}
        self.current_id = ""
        for item in (part.strip() for part in spec.split(",")):
            if not item:
                continue
            key_id, _, encoded = item.partition(":")
            try:
                key = base64.b64decode(encoded, validate=True)
            except (binascii.Error, ValueError) as exc:
                raise ValueError(f"encryption key {key_id!r} is not valid base64") from exc
            if not key_id or len(key_id) > 32 or len(key) != 32:
                raise ValueError("each encryption key needs an id (1-32 chars) and 32 bytes")
            self._keys[key_id] = key
            self.current_id = self.current_id or key_id
        if not self._keys:
            raise ValueError("no encryption keys configured")

    def encrypt(self, plaintext: bytes, aad: bytes = b"") -> bytes:
        key_id = self.current_id.encode()
        nonce = os.urandom(12)
        ciphertext = AESGCM(self._keys[self.current_id]).encrypt(nonce, plaintext, aad)
        return bytes([_VERSION, len(key_id)]) + key_id + nonce + ciphertext

    def decrypt(self, blob: bytes, aad: bytes = b"") -> bytes:
        if len(blob) < 2 or blob[0] != _VERSION:
            raise ValueError("unsupported ciphertext format")
        id_len = blob[1]
        key_id = blob[2 : 2 + id_len].decode()
        nonce = blob[2 + id_len : 14 + id_len]
        key = self._keys.get(key_id)
        if key is None:
            raise ValueError(f"unknown encryption key id {key_id!r}")
        return AESGCM(key).decrypt(nonce, blob[14 + id_len :], aad)


@lru_cache
def get_keyring() -> Keyring:
    spec = get_settings().encryption_keys.get_secret_value()
    if not spec:
        raise RuntimeError("ENCRYPTION_KEYS is not configured (see backend/.env.example)")
    return Keyring(spec)
