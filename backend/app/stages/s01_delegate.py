"""Stage 1 - DELEGATE. The human sets the mandate; its digest becomes the lineage root."""

import uuid

from ..core.ledger import EvidenceLedger
from ..core.lineage import mandate_lineage
from ..domain.models import Mandate

STAGE = "1-delegate"


def register_mandate(ledger: EvidenceLedger, mandate: Mandate, delegation_id: str | None = None) -> str:
    digest = mandate.digest()
    delegation_id = delegation_id or uuid.uuid4().hex
    lid = mandate_lineage(digest, delegation_id)
    ledger.append(lid, STAGE, "mandate", {"digest": digest, "delegation_id": delegation_id, "mandate": mandate.model_dump(mode="json")})
    return lid
