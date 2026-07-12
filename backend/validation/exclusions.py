"""Enumerated exclusion reason codes for prediction_log.

Every exclusion writer must use one of these codes — free-text reasons are
no longer allowed (andon finding A1). Exclusion is append-only: once a row
carries excluded_from_stats=1 there is NO un-exclude path anywhere in the
system; database.mark_excluded() is the only sanctioned single-row writer
and it refuses to clear an existing exclusion.

The codes are deliberately duplicated as string literals inside
scripts/verify/ (independence rule — those scripts import nothing from
backend/). If a code is added here, add the literal there too.
"""

from __future__ import annotations

# minimum-confidence guard forced neutral — the system had no signal at all
GARBAGE_CONFIDENCE_ZERO = "GARBAGE_CONFIDENCE_ZERO"

# confidence above zero but below the 5% noise floor (_MIN_STAT_CONFIDENCE)
GARBAGE_CONFIDENCE_SUBFLOOR = "GARBAGE_CONFIDENCE_SUBFLOOR"

EXCLUSION_CODES: frozenset[str] = frozenset(
    {GARBAGE_CONFIDENCE_ZERO, GARBAGE_CONFIDENCE_SUBFLOOR}
)
