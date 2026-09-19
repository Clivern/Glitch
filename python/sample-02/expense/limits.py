# All values are integer cents. These ceilings are enforced only by
# expense.policy.assert_payout_allowed — ledger posting does not re-check them.

SINGLE_PAYOUT_CENTS = 100_000  # $1,000
DAILY_PAYOUT_CENTS = 250_000  # $2,500
NEW_ACCOUNT_DAILY_CENTS = 25_000  # $250
