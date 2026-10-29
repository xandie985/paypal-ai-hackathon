"""One identity thread: mandate digest -> lineage ID -> every PayPal call.

The lineage ID rides in Orders `custom_id`, the invoice reference, the payout
`sender_batch_id` and every ledger entry, so a dispute can be traced back to the
mandate that authorized the spend (the Issue 113 lineage gap).
"""

from .canonical import sha256_hex


def mandate_lineage(mandate_digest: str) -> str:
    return f"PG-{mandate_digest[:16]}"


def txn_lineage(mandate_lid: str, *parts) -> str:
    """Per-transaction lineage, prefixed by its mandate so queries can roll up."""
    return f"{mandate_lid}.{sha256_hex([mandate_lid, *parts])[:10]}"


def request_id(lineage_id: str, stage: str, operation: str, *parts) -> str:
    """Deterministic PayPal-Request-Id. A retry of the same operation derives the
    same ID, so PayPal returns the original result instead of charging twice."""
    return f"{stage}-{operation}-{sha256_hex([lineage_id, stage, operation, *parts])[:40]}"
