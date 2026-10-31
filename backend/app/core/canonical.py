"""Canonical JSON + hashing. Every digest in the system goes through here so the
same object always hashes the same way (sorted keys, no whitespace, Decimals as strings)."""

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel


def _default(o):
    if isinstance(o, Decimal):
        return format(o, "f")
    if isinstance(o, (date, datetime)):
        return o.isoformat()
    if isinstance(o, BaseModel):
        return o.model_dump(mode="json")
    raise TypeError(f"not canonicalizable: {type(o).__name__}")


def canonical_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=_default, ensure_ascii=False)


def sha256_hex(obj) -> str:
    data = obj if isinstance(obj, bytes) else canonical_json(obj).encode()
    return hashlib.sha256(data).hexdigest()
