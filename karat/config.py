"""Correction knobs (see data_contract.md). Tune later; do not scatter
magic numbers through the logic."""

# Campaigns with fewer mature leads than this are "low confidence" and
# excluded from the leaking ranking.
MIN_LEADS = 30

# Leads newer than this many days (relative to window end) are excluded from
# revenue/match calcs — not enough time to sell. Reported as pending instead.
LAG_DAYS = 7
