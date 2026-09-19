from __future__ import annotations

from datetime import datetime, timezone

from expense.accounts import AccountStore
from expense.ledger import Entry, Ledger
from expense.money import Money
from expense.policy import assert_payout_allowed


def create_payout(
    store: AccountStore,
    ledger: Ledger,
    *,
    source_id: int,
    dest_id: int,
    amount: Money,
    ref: str,
    now: datetime | None = None,
) -> Entry:
    """Only supported way to move contractor funds.

    Batch settlement and any new API should call this, not Ledger.transfer.
    """
    now = now or datetime.now(timezone.utc)
    source = store.get(source_id)
    dest = store.get(dest_id)
    assert_payout_allowed(source, dest, amount, now=now)
    return ledger.transfer(source, dest, amount, now=now, ref=ref)
