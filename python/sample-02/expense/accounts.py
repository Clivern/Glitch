from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum

from expense.money import Money


# IDs at or below this value are clearing/sweep accounts. User-facing payouts
# must never use them as a destination; funds sent there are not reversible
# through the payout API.
SYSTEM_ACCOUNT_MAX_ID = 99

NEW_ACCOUNT_AGE = timedelta(days=14)


class AccountType(Enum):
    USER = "user"
    MERCHANT = "merchant"
    SYSTEM = "system"


class AccountStatus(Enum):
    ACTIVE = "active"
    FROZEN = "frozen"


@dataclass
class Account:
    id: int
    type: AccountType
    currency: str
    opened_at: datetime
    status: AccountStatus = AccountStatus.ACTIVE
    verified: bool = False
    ledger_cents: int = 0
    hold_cents: int = 0
    payouts_today_cents: int = 0

    @property
    def available_cents(self) -> int:
        return self.ledger_cents - self.hold_cents

    def is_new(self, now: datetime) -> bool:
        return now - self.opened_at < NEW_ACCOUNT_AGE

    def is_system(self) -> bool:
        return self.type is AccountType.SYSTEM or self.id <= SYSTEM_ACCOUNT_MAX_ID

    def can_receive_user_payout(self) -> bool:
        if self.status is AccountStatus.FROZEN:
            return False
        if self.is_system():
            return False
        if self.type is AccountType.MERCHANT and not self.verified:
            return False
        return True


@dataclass
class AccountStore:
    accounts: dict[int, Account] = field(default_factory=dict)

    def add(self, account: Account) -> Account:
        if account.id in self.accounts:
            raise ValueError(f"duplicate account {account.id}")
        self.accounts[account.id] = account
        return account

    def get(self, account_id: int) -> Account:
        try:
            return self.accounts[account_id]
        except KeyError as exc:
            raise KeyError(f"unknown account {account_id}") from exc

    def seed_demo(self, now: datetime | None = None) -> None:
        now = now or datetime.now(timezone.utc)
        self.add(
            Account(
                id=1,
                type=AccountType.SYSTEM,
                currency="USD",
                opened_at=now - timedelta(days=400),
                verified=True,
                ledger_cents=0,
            )
        )
        self.add(
            Account(
                id=200,
                type=AccountType.USER,
                currency="USD",
                opened_at=now - timedelta(days=200),
                verified=True,
                ledger_cents=5_000_00,
            )
        )
        self.add(
            Account(
                id=300,
                type=AccountType.MERCHANT,
                currency="USD",
                opened_at=now - timedelta(days=80),
                verified=True,
                ledger_cents=0,
            )
        )
        self.add(
            Account(
                id=301,
                type=AccountType.MERCHANT,
                currency="USD",
                opened_at=now - timedelta(days=3),
                verified=False,
                ledger_cents=0,
            )
        )


def debit_available(account: Account, amount: Money) -> None:
    if account.currency != amount.currency:
        raise ValueError("currency mismatch")
    if account.available_cents < amount.amount_cents:
        raise ValueError("insufficient available balance")
    account.ledger_cents -= amount.amount_cents


def credit_ledger(account: Account, amount: Money) -> None:
    if account.currency != amount.currency:
        raise ValueError("currency mismatch")
    account.ledger_cents += amount.amount_cents
