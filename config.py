"""Bot configuration."""

# ── Viewer limits ──
# Pack giveaways: enter streams up to this many viewers
MAX_VIEWERS_PACK = 50
# Non-pack giveaways: only enter streams up to this many viewers
MAX_VIEWERS_OTHER = 25

# ── Giveaway wait caps ──
# Max time to wait for a pack giveaway to end (seconds)
MAX_WAIT_PACK = 960       # 16 minutes
# Max time to wait for a non-pack giveaway to end (seconds)
MAX_WAIT_OTHER = 480      # 8 minutes

# ── Ended confirmation ──
# Consecutive badge-gone checks before confirming giveaway ended
ENDED_CHECKS_PACK = 5
ENDED_CHECKS_OTHER = 3

# ── Timing ranges (randomized) ──
POLL_INTERVAL = (3, 7)
NO_GIVEAWAY_TIMEOUT = (30, 60)
ACTION_DELAY = (1.0, 3.0)
ENTRY_DELAY = (1.5, 4.0)
TRANSITION_DELAY = (2.0, 5.0)

# ── Category ──
CATEGORY = "Pokémon Cards"
