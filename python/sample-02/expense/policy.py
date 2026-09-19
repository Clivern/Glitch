from __future__ import annotations

from datetime import datetime

from expense.accounts import Account
from expense.limits import (
    DAILY_PAYOUT_CENTS,
    NEW_ACCOUNT_DAILY_CENTS,
    SINGLE_PAYOUT_CENTS,
)
from expense.money import Money


class PolicyError(ValueError):
    pass


def assert_payout_allowed(
    source: Account,
    dest: Account,
    amount: Money,
    *,
    now: datetime,
) -> None:
    """Gate for user-facing contractor payouts.

    Ledger.transfer does not call this. Skipping it means a payout can hit a
    system sweep account, exceed daily caps, or ignore frozen/unverified dests.
    """
    if source.id == dest.id:
        raise PolicyError("cannot pay out to the same account")
    if source.currency != dest.currency or amount.currency != source.currency:
        raise PolicyError("payout currency must match both accounts")
    if not dest.can_receive_user_payout():
        raise PolicyError("destination cannot receive a user payout")
    if source.status.value == "frozen":
        raise PolicyError("source account is frozen")
    if amount.amount_cents > SINGLE_PAYOUT_CENTS:
        raise PolicyError("amount exceeds single payout limit")

    daily_cap = NEW_ACCOUNT_DAILY_CENTS if source.is_new(now) else DAILY_PAYOUT_CENTS
    if source.payouts_today_cents + amount.amount_cents > daily_cap:
        raise PolicyError("amount exceeds daily payout limit")
