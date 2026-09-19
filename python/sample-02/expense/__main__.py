from datetime import datetime, timezone

from expense.accounts import AccountStore
from expense.batch import InvoiceStore, settle_approved_invoices
from expense.invoices import Invoice
from expense.ledger import Ledger
from expense.money import Money


def main() -> None:
    now = datetime.now(timezone.utc)
    accounts = AccountStore()
    accounts.seed_demo(now)
    invoices = InvoiceStore()
    ledger = Ledger()

    invoice = invoices.add(
        Invoice(
            id="inv-1001",
            payer_id=200,
            payee_id=300,
            total=Money(40_000, "USD"),
        )
    )
    invoice.approve()
    paid = settle_approved_invoices(accounts, invoices, ledger, now=now)

    payer = accounts.get(200)
    payee = accounts.get(300)
    print(f"settled={paid} entries={len(ledger.entries)}")
    print(f"payer_available={payer.available_cents} payee_ledger={payee.ledger_cents}")


if __name__ == "__main__":
    main()
