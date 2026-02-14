"""Bot configuration."""

# Maximum viewer count to consider a stream "low volume"
MAX_VIEWERS = 50

# Poll interval range for UI checks (seconds) — randomized each cycle
POLL_INTERVAL = (3, 7)

# How long to stay in a stream before leaving if no giveaway appears (seconds)
NO_GIVEAWAY_TIMEOUT = (30, 60)

# How long to wait after entering a giveaway for results (seconds)
GIVEAWAY_RESULT_TIMEOUT = (180, 360)

# Delay range between major actions like taps/navigations (seconds)
ACTION_DELAY = (1.0, 3.0)

# Delay range before entering a giveaway after detecting it (seconds)
ENTRY_DELAY = (1.5, 4.0)

# Delay range after leaving a stream before finding the next one (seconds)
TRANSITION_DELAY = (2.0, 5.0)

# Category to search in
CATEGORY = "Pokémon Cards"

# Keywords in stream titles that suggest giveaways
GIVEAWAY_KEYWORDS = [
    "giveaway", "givvy", "givvys", "givvies", "giv",
    "free", "raffle", "give away", "give-away",
]
