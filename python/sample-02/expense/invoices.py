from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from expense.money import Money


class InvoiceStatus(Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    PAID = "paid"


@dataclass
class Invoice:
    """A contractor invoice is paid exactly once, in full, by the nightly job.

    Status stays APPROVED until batch.settle_approved_invoices marks it PAID.
    Do not disburse an approved invoice from any other path — the batch job
    will pay every remaining APPROVED invoice at its full `total`.
    """

    id: str
    payer_id: int
    payee_id: int
    total: Money
    status: InvoiceStatus = InvoiceStatus.DRAFT

    def approve(self) -> None:
        if self.status is not InvoiceStatus.DRAFT:
            raise ValueError("only draft invoices can be approved")
        self.status = InvoiceStatus.APPROVED

    def mark_paid(self) -> None:
        if self.status is not InvoiceStatus.APPROVED:
            raise ValueError("only approved invoices can be marked paid")
        self.status = InvoiceStatus.PAID

    @property
    def ledger_ref(self) -> str:
        return f"invoice:{self.id}"
