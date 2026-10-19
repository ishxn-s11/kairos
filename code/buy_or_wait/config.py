"""Engine-wide configuration: monetary precision, forecast horizon, inference policy."""

from __future__ import annotations

from decimal import Decimal, getcontext

getcontext().prec = 50

# 90-day safety horizon (problem_statement.md).
FORECAST_DAYS = 90

# Currencies with cents; others are recorded with their conventional unit precision.
MINOR_UNIT_CURRENCIES = {"USD", "EUR"}

# Recurring-expense inference (AGENTS.md 6.3: detect recurrence only when
# history supports it; forecast essential variable spending conservatively).
RECURRENCE_MIN_OBSERVATIONS = 3
RECURRENCE_TOLERANCE = Decimal("0.15")  # +/-15% around the median amount
RECURRENCE_INTERVAL_TOLERANCE_DAYS = 4  # median interval +/- days
VARIABLE_ESSENTIAL_MONTHLY_MULTIPLIER = 1.2  # 120% of observed monthly median

# Stoppables are dropped from future projections entirely; reducible ones are
# only ever reduced explicitly through spending_changes_needed.
