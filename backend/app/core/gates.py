"""Gate tokens: HMAC-signed proofs that a stage passed, bound to one lineage.

Stage 7 cannot pay out without a VERIFIED token from stage 5 and a RECONCILED token
from stage 6. A token minted for one transaction can't be replayed on another.
"""

import hashlib
import hmac

from .errors import GateTokenInvalid

VERIFIED = "VERIFIED"
RECONCILED = "RECONCILED"
APPROVED = "APPROVED"


def _sig(secret: str, gate: str, lineage_id: str, subject: str) -> str:
    return hmac.new(secret.encode(), f"{gate}|{lineage_id}|{subject}".encode(), hashlib.sha256).hexdigest()[:32]


def issue(secret: str, gate: str, lineage_id: str, subject: str) -> str:
    return f"{gate}:{subject}:{_sig(secret, gate, lineage_id, subject)}"


def require(secret: str, token: str | None, gate: str, lineage_id: str, subject: str) -> None:
    if not token:
        raise GateTokenInvalid(f"missing {gate} token", gate=gate, lineage_id=lineage_id)
    try:
        g, s, sig = token.split(":")
    except ValueError:
        raise GateTokenInvalid("malformed gate token", gate=gate) from None
    if g != gate or s != subject or not hmac.compare_digest(sig, _sig(secret, gate, lineage_id, subject)):
        raise GateTokenInvalid(f"{gate} token not valid for {lineage_id}/{subject}", gate=gate, lineage_id=lineage_id)
