"""Canonical JSON identity for immutable captured resources."""
import hashlib
import json
from uuid import uuid4

def encode(value) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (ValueError, TypeError, RecursionError) as exc:
        raise ValueError("Chart data must be finite JSON values") from exc


def digest(value) -> str:
    return hashlib.sha256(encode(value).encode()).hexdigest()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"
