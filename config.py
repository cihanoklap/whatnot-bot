"""Bot configuration."""

# ── Default config (used by server for serialization) ──
DEFAULT_CONFIG = {
    "mode": "normal",              # "normal" or "lowest_viewer"
    "max_viewers_pack": 40,
    "max_viewers_other": 20,
    "max_wait_pack": 960,          # seconds (16 minutes)
    "max_wait_other": 480,         # seconds (8 minutes)
    "ended_checks_pack": 5,
    "ended_checks_other": 5,
    "category": "Pokémon Cards",
}

# ── Viewer limits ──
# Pack giveaways: enter streams up to this many viewers
MAX_VIEWERS_PACK = DEFAULT_CONFIG["max_viewers_pack"]
# Non-pack giveaways: only enter streams up to this many viewers
MAX_VIEWERS_OTHER = DEFAULT_CONFIG["max_viewers_other"]

# ── Giveaway wait caps ──
# Max time to wait for a pack giveaway to end (seconds)
MAX_WAIT_PACK = DEFAULT_CONFIG["max_wait_pack"]
# Max time to wait for a non-pack giveaway to end (seconds)
MAX_WAIT_OTHER = DEFAULT_CONFIG["max_wait_other"]

# ── Ended confirmation ──
# Consecutive badge-gone checks before confirming giveaway ended
ENDED_CHECKS_PACK = DEFAULT_CONFIG["ended_checks_pack"]
ENDED_CHECKS_OTHER = DEFAULT_CONFIG["ended_checks_other"]

# ── Timing ranges (randomized) ──
POLL_INTERVAL = (3, 7)
NO_GIVEAWAY_TIMEOUT = (30, 60)
ACTION_DELAY = (1.0, 3.0)
ENTRY_DELAY = (1.5, 4.0)
TRANSITION_DELAY = (2.0, 5.0)

# ── Category ──
CATEGORY = DEFAULT_CONFIG["category"]
