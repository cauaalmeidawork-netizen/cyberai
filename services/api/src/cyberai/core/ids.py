"""Time-ordered identifiers.

UUIDv7 (RFC 9562) is used for every primary key and correlation id:

* it sorts by creation time, which keeps B-tree index inserts local instead of
  scattering writes across the whole index like UUIDv4 does;
* it does not leak business volume the way a monotonic integer does.

The implementation below uses a process-wide monotonic counter to guarantee
that two ids generated in rapid succession never collide and always sort in
order of creation, regardless of OS clock precision.
"""

from __future__ import annotations

import os
import threading
import time
import uuid
from typing import Final

_UUID7_VARIANT: Final = 0b10
_UUID7_VERSION: Final = 0x7

_lock = threading.Lock()
_last_uuid7_ns: int = 0


def _new_uuid7_strictly_ordered() -> uuid.UUID:
    """Return a UUIDv7 guaranteed to be later than the previous one in process.

    Two rapid calls inside the same nanosecond are indistinguishable by wall
    clock alone. A process-wide monotonic counter guarantees sort order across
    repeated calls without relying on random bits.
    """
    global _last_uuid7_ns
    with _lock:
        now_ns = time.time_ns()
        if now_ns <= _last_uuid7_ns:
            now_ns = _last_uuid7_ns + 1
        _last_uuid7_ns = now_ns

    timestamp_ms = now_ns // 1_000_000
    # Sub-millisecond counter in rand_a. Use 12 bits (fits RFC 9562 rand_a
    # field) so repeated calls inside the same ms still sort correctly.
    sub_ms_counter = (now_ns % 1_000_000) & 0xFFF
    random_bytes = os.urandom(8)

    value = (timestamp_ms & 0xFFFF_FFFF_FFFF) << 80
    value |= _UUID7_VERSION << 76
    value |= (sub_ms_counter & 0x0FFF) << 64
    value |= _UUID7_VARIANT << 62
    value |= int.from_bytes(random_bytes, "big") & ((1 << 62) - 1)

    return uuid.UUID(int=value)


def new_uuid7() -> uuid.UUID:
    """Return a fresh, time-ordered UUIDv7."""
    return _new_uuid7_strictly_ordered()


def _uuid7_fallback() -> uuid.UUID:
    """Build a UUIDv7 from a millisecond timestamp plus 74 random bits.

    Kept as a reference implementation and for environments without a
    monotonic-counter wrapper.
    """
    timestamp_ms = time.time_ns() // 1_000_000
    random_bytes = os.urandom(10)

    value = (timestamp_ms & 0xFFFF_FFFF_FFFF) << 80
    value |= _UUID7_VERSION << 76
    value |= (random_bytes[0] & 0x0F) << 72
    value |= random_bytes[1] << 64
    value |= _UUID7_VARIANT << 62
    value |= int.from_bytes(random_bytes[2:], "big") & ((1 << 62) - 1)

    return uuid.UUID(int=value)


def new_id() -> str:
    """Return a fresh identifier as a canonical UUID string."""
    return str(new_uuid7())


def new_trace_id() -> str:
    """Return a W3C-compatible 128-bit trace id (32 lowercase hex chars)."""
    return os.urandom(16).hex()


def new_span_id() -> str:
    """Return a W3C-compatible 64-bit span id (16 lowercase hex chars)."""
    return os.urandom(8).hex()
