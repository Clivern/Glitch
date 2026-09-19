from __future__ import annotations

from dataclasses import dataclass


SUPPORTED_CURRENCIES = frozenset({"USD", "EUR"})


@dataclass(frozen=True)
class Money:
    """Integer minor units only. Callers must never pass major-unit floats."""

    amount_cents: int
    currency: str

    def __post_init__(self) -> None:
        if not isinstance(self.amount_cents, int) or isinstance(self.amount_cents, bool):
            raise TypeError("amount_cents must be an int")
        if self.amount_cents <= 0:
            raise ValueError("amount must be positive")
        if self.currency not in SUPPORTED_CURRENCIES:
            raise ValueError(f"unsupported currency: {self.currency}")

    def add(self, other: Money) -> Money:
        self._same_currency(other)
        return Money(self.amount_cents + other.amount_cents, self.currency)

    def _same_currency(self, other: Money) -> None:
        if self.currency != other.currency:
            raise ValueError("currency mismatch")
