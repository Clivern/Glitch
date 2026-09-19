from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from expense.accounts import AccountStore
from expense.invoices import Invoice, InvoiceStatus
from expense.ledger import Ledger
from expense.payouts import create_payout


@dataclass
class InvoiceStore:
    invoices: dict[str, Invoice] = field(default_factory=dict)

    def add(self, invoice: Invoice) -> Invoice:
        if invoice.id in self.invoices:
            raise ValueError(f"duplicate invoice {invoice.id}")
        self.invoices[invoice.id] = invoice
        return invoice

    def approved(self) -> list[Invoice]:
        return [
            invoice
            for invoice in self.invoices.values()
            if invoice.status is InvoiceStatus.APPROVED
        ]


def settle_approved_invoices(
    accounts: AccountStore,
    invoices: InvoiceStore,
    ledger: Ledger,
    *,
    now: datetime | None = None,
) -> int:
    """Nightly settlement. Pays each approved invoice in full exactly once.

    The job is the sole payer for APPROVED invoices. It assumes nobody else
    has already disbursed those funds. A new "pay now" or "pay partial"
    helper that leaves status=APPROVED will be paid again here.
    """
    now = now or datetime.now(timezone.utc)
    paid = 0
    for invoice in invoices.approved():
        create_payout(
            accounts,
            ledger,
            source_id=invoice.payer_id,
            dest_id=invoice.payee_id,
            amount=invoice.total,
            ref=invoice.ledger_ref,
            now=now,
        )
        invoice.mark_paid()
        paid += 1
    return paid
