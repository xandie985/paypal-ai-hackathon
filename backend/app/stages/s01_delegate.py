"""Stage 1 - DELEGATE. The human sets the mandate; its digest becomes the lineage root."""

from ..core.ledger import EvidenceLedger
from ..core.lineage import mandate_lineage
from ..domain.models import Mandate

STAGE = "1-delegate"


def register_mandate(ledger: EvidenceLedger, mandate: Mandate) -> str:
    digest = mandate.digest()
    lid = mandate_lineage(digest)
    ledger.append(lid, STAGE, "mandate", {"digest": digest, "mandate": mandate.model_dump(mode="json")})
    return lid
