"""Time-ordered UUIDs (RFC 9562 version 7).

UUIDv7 keeps B-tree indexes compact (new rows append at the end) and lets clients,
including the future offline mobile app, generate IDs without asking the server.
"""

import os
import time
import uuid

_RAND_A_MASK = (1 << 12) - 1
_RAND_B_MASK = (1 << 62) - 1


def uuid7() -> uuid.UUID:
    timestamp_ms = time.time_ns() // 1_000_000
    random_bits = int.from_bytes(os.urandom(10), "big")  # 80 random bits
    rand_a = (random_bits >> 62) & _RAND_A_MASK
    rand_b = random_bits & _RAND_B_MASK
    value = (
        (timestamp_ms & ((1 << 48) - 1)) << 80
        | 0x7 << 76  # version 7
        | rand_a << 64
        | 0b10 << 62  # RFC 4122 variant
        | rand_b
    )
    return uuid.UUID(int=value)
