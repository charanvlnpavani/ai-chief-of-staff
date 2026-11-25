"""Unit tests for core helpers: ids, crypto, signed payloads, cursors, logging redaction."""

import base64
import json
import logging
import time

import pytest

from app.core.crypto import Keyring
from app.core.errors import BadRequest
from app.core.ids import uuid7
from app.core.logging import JsonFormatter, redact
from app.core.pagination import decode_cursor, encode_cursor, next_cursor
from app.core.security import hash_token, ip_prefix, pkce_pair, sign_payload, verify_payload

KEY_A = "a:" + base64.b64encode(b"A" * 32).decode()
KEY_B = "b:" + base64.b64encode(b"B" * 32).decode()


def test_uuid7_has_version_7_and_rfc_variant() -> None:
    value = uuid7()
    assert value.version == 7
    assert value.variant == "specified in RFC 4122"


def test_uuid7_is_time_ordered() -> None:
    first = uuid7()
    time.sleep(0.002)
    second = uuid7()
    assert first < second


def test_encryption_round_trip_and_aad_binding() -> None:
    ring = Keyring(KEY_A)
    blob = ring.encrypt(b"private note", aad=b"row-1")
    assert b"private note" not in blob
    assert ring.decrypt(blob, aad=b"row-1") == b"private note"
    with pytest.raises(Exception):  # noqa: B017, PT011 - cryptography raises InvalidTag
        ring.decrypt(blob, aad=b"row-2")


def test_key_rotation_keeps_old_blobs_readable() -> None:
    old_blob = Keyring(KEY_A).encrypt(b"before rotation")
    rotated = Keyring(f"{KEY_B},{KEY_A}")  # new key first
    assert rotated.decrypt(old_blob) == b"before rotation"
    assert rotated.current_id == "b"


def test_keyring_rejects_short_keys() -> None:
    with pytest.raises(ValueError, match="32 bytes"):
        Keyring("x:" + base64.b64encode(b"short").decode())


def test_signed_payload_round_trip_and_tamper_detection() -> None:
    token = sign_payload({"state": "abc"}, "secret", ttl_seconds=60)
    assert verify_payload(token, "secret")["state"] == "abc"
    with pytest.raises(ValueError, match="bad signature"):
        verify_payload(token, "other-secret")
    encoded, signature = token.split(".")
    with pytest.raises(ValueError, match="bad signature"):
        verify_payload(encoded + "x." + signature, "secret")


def test_signed_payload_expires() -> None:
    token = sign_payload({"state": "abc"}, "secret", ttl_seconds=-1)
    with pytest.raises(ValueError, match="expired"):
        verify_payload(token, "secret")


def test_pkce_challenge_is_s256_of_verifier() -> None:
    import hashlib

    verifier, challenge = pkce_pair()
    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=")
    assert challenge == expected.decode()
    assert 43 <= len(verifier) <= 128


def test_hash_token_is_stable_and_not_plaintext() -> None:
    assert hash_token("abc") == hash_token("abc")
    assert hash_token("abc") != b"abc"


def test_cursor_round_trip_and_validation() -> None:
    assert decode_cursor(encode_cursor(40)) == 40
    assert decode_cursor(None) == 0
    assert next_cursor(0, 20, 21) == encode_cursor(20)
    assert next_cursor(0, 20, 20) is None
    with pytest.raises(BadRequest):
        decode_cursor("not-a-cursor")


def test_ip_prefix_truncates() -> None:
    assert ip_prefix("203.0.113.77") == "203.0.113.0/24"
    assert ip_prefix("2001:db8:abcd:1234::1") == "2001:db8:abcd::/48"
    assert ip_prefix("garbage") is None


def test_log_redaction() -> None:
    assert redact({"token": "abc", "user_id": "u1"}) == {"token": "[REDACTED]", "user_id": "u1"}
    record = logging.LogRecord("t", logging.INFO, "f", 1, "login", None, None)
    record.session_token = "super-secret"
    record.path = "/api/v1/auth"
    output = json.loads(JsonFormatter().format(record))
    assert output["session_token"] == "[REDACTED]"
    assert output["path"] == "/api/v1/auth"
