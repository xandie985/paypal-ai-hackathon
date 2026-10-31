"""Stage 6 - RECONCILE. Invoice forensics before any payout:
3-way match (vendor invoice vs sealed PO vs delivery proof), payee spoof check, and
duplicate detection with a hybrid lexical (BM25) + character-trigram similarity.

The trigram vector is a dependency-free stand-in for embeddings: it can't collapse
"INV-1001" and "INV-1010" into the same point the way sentence embeddings tend to,
which is the 'embedding collapse' blocker for invoice numbers.
"""

import math
import re
from collections import Counter
from decimal import Decimal

from ..core.gates import RECONCILED, issue
from ..core.ledger import EvidenceLedger
from ..domain.models import VendorInvoice

STAGE = "6-reconcile"
DUP_THRESHOLD = 0.85


def _norm_number(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower()).lstrip("0")


def _tokens(s: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", s.lower())


def _trigrams(s: str) -> Counter:
    s = f"  {s.lower()} "
    return Counter(s[i : i + 3] for i in range(len(s) - 2))


def _cos(a: Counter, b: Counter) -> float:
    dot = sum(a[k] * b[k] for k in a)
    na, nb = math.sqrt(sum(v * v for v in a.values())), math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na and nb else 0.0


def _bm25(query: list[str], docs: list[list[str]], k1=1.5, b=0.75) -> list[float]:
    n = len(docs)
    avg = sum(map(len, docs)) / n if n else 0
    df = Counter(t for d in docs for t in set(d))
    scores = []
    for d in docs:
        tf = Counter(d)
        s = 0.0
        for t in query:
            if t in tf:
                idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
                s += idf * tf[t] * (k1 + 1) / (tf[t] + k1 * (1 - b + b * len(d) / avg))
        scores.append(s)
    return scores


class InvoiceForensics:
    def __init__(self, vendor_registry: dict[str, str]):
        self.vendor_registry = vendor_registry  # vendor -> registered payee email
        self.seen: list[VendorInvoice] = []

    def _doc(self, inv: VendorInvoice) -> str:
        return f"{inv.vendor} {inv.invoice_number} {inv.amount} {inv.memo}"

    def duplicates(self, inv: VendorInvoice) -> list[dict]:
        if not self.seen:
            return []
        docs = [_tokens(self._doc(s)) for s in self.seen]
        lex = _bm25(_tokens(self._doc(inv)), docs)
        top = max(lex) or 1.0
        hits = []
        for s, lex_score in zip(self.seen, lex, strict=True):
            exact = s.vendor == inv.vendor and _norm_number(s.invoice_number) == _norm_number(inv.invoice_number)
            score = 0.5 * (lex_score / top) + 0.5 * _cos(_trigrams(self._doc(s)), _trigrams(self._doc(inv)))
            if exact or (score >= DUP_THRESHOLD and s.amount == inv.amount and s.vendor == inv.vendor):
                hits.append({"invoice_number": s.invoice_number, "score": round(score, 3), "exact": exact})
        return hits

    def check(self, ledger: EvidenceLedger, secret: str, inv: VendorInvoice) -> dict:
        flags = []
        seal = ledger.latest(inv.lineage_id, "seal")
        proof = ledger.latest(inv.lineage_id, "delivery_proof")
        if seal is None:
            flags.append("NO_PO: no sealed order for this lineage")
        elif Decimal(seal.payload["amount"]) != inv.amount:
            flags.append(f"AMOUNT_MISMATCH: invoice {inv.amount} vs PO {seal.payload['amount']}")
        if proof is None or proof.payload["verdict"] != "PASS":
            flags.append("NO_DELIVERY_PROOF")
        registered = self.vendor_registry.get(inv.vendor)
        if registered is None:
            flags.append("UNKNOWN_VENDOR")
        elif registered.lower() != inv.payee_email.lower():
            flags.append(f"PAYEE_MISMATCH: {inv.payee_email} is not the registered payee")
        dups = self.duplicates(inv)
        if dups:
            flags.append(f"DUPLICATE: matches {[d['invoice_number'] for d in dups]}")

        self.seen.append(inv)
        status = "CLEAN" if not flags else "FLAGGED"
        ledger.append(inv.lineage_id, STAGE, "reconciliation", {"invoice": inv.model_dump(mode="json"), "status": status, "flags": flags})
        token = issue(secret, RECONCILED, inv.lineage_id, inv.invoice_number) if status == "CLEAN" else None
        return {"status": status, "flags": flags, "token": token}
