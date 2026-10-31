import os

os.environ["REPLAY_MODE"] = "true"  # tests never touch the sandbox, whatever .env says

from decimal import Decimal

import pytest

from app.core.ledger import EvidenceLedger
from app.domain.models import Mandate
from app.integrations.paypal import ReplayPayPal

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
