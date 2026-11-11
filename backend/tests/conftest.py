import os
import tempfile

os.environ["REPLAY_MODE"] = "true"  # tests never touch the sandbox, whatever .env says
# Tests that switch to live rules still write a "persistent" ledger. Point it at a throwaway file so
# pytest can never append test runs to the real evidence ledger (./ledger.db).
_TEST_LEDGER_DIR = tempfile.mkdtemp(prefix="pactguard-test-ledger-")
os.environ["LEDGER_PATH"] = os.path.join(_TEST_LEDGER_DIR, "ledger.db")

from decimal import Decimal  # noqa: E402 (env must be set before app imports)

import pytest  # noqa: E402

from app.core.ledger import EvidenceLedger  # noqa: E402
from app.domain.models import Mandate  # noqa: E402
from app.integrations.paypal import ReplayPayPal  # noqa: E402

SECRET = "test-secret"


@pytest.fixture
def ledger():
    return EvidenceLedger(":memory:")


@pytest.fixture
def gateway():
    return ReplayPayPal()


@pytest.fixture
def mandate():
    return Mandate(
        principal="ops@acme.example",
        purpose="test",
        budget=Decimal("2000"),
        auto_threshold=Decimal("300"),
        per_txn_cap=Decimal("1500"),
        vendor_allowlist=["Northwind Displays", "Contoso Retail"],
        allowed_categories=["monitors", "webcams"],
        min_return_days=30,
    )
