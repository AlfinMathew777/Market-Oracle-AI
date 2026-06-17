"""Shared validation constants.

One home for the outcome noise band so the resolver, its inline direction
re-derivation, and the reputation update rule can never disagree on what counts
as a real move.
"""

# move smaller than this (percent) is noise, not a directional outcome.
MIN_MOVE_PCT = 0.5
