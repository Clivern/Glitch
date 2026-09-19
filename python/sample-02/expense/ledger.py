from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from expense.accounts import Account, credit_ledger, debit_available
from expense.money import Money


@dataclass(frozen=True)
class Entry:
    source_id: int
    dest_id: int
    amount_cents: int
    currency: str
    posted_at: datetime
    ref: str


@dataclass
class Ledger:
    """Append-only movement of balances.

    This module does not enforce payout policy. Destination checks, daily
    limits, frozen accounts, and invoice settlement rules live elsewhere.
    Callers that post here directly are responsible for those invariants.
    """

    entries: list[Entry] = field(default_factory=list)

    def transfer(
        self,
        source: Account,
        dest: Account,
        amount: Money,
        *,
        now: datetime,
        ref: str,
    ) -> Entry:
        if any(entry.ref == ref for entry in self.entries):
            raise ValueError(f"duplicate ledger ref {ref}")

        debit_available(source, amount)
        credit_ledger(dest, amount)
        source.payouts_today_cents += amount.amount_cents

        entry = Entry(
            source_id=source.id,
            dest_id=dest.id,
            amount_cents=amount.amount_cents,
            currency=amount.currency,
            posted_at=now,
            ref=ref,
        )
        self.entries.append(entry)
        return entry
