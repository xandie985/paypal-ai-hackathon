"""pytest must never write to the real evidence ledger."""

import os


def test_suite_never_uses_the_real_ledger_file():
    from app.config import settings

    assert os.path.basename(os.path.dirname(settings.ledger_path)).startswith("pactguard-test-ledger-")
    assert os.path.abspath(settings.ledger_path) != os.path.abspath("ledger.db")
