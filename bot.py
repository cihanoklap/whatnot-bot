"""
Whatnot Giveaway Bot
Finds low-viewer Pokemon card streams, enters giveaways,
waits for results, and moves on.
"""

import uiautomator2 as u2
import time
import random
import re
import logging
from config import (
    MAX_VIEWERS, POLL_INTERVAL, NO_GIVEAWAY_TIMEOUT,
    GIVEAWAY_RESULT_TIMEOUT, ACTION_DELAY, ENTRY_DELAY,
    TRANSITION_DELAY, CATEGORY,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("whatnot-bot")

# How often to check if a giveaway is still running (seconds)
GIVEAWAY_CHECK_INTERVAL = (8, 13)

# How long to wait after a giveaway ends to see if a new one starts (seconds)
NEW_GIVEAWAY_WAIT = (15, 30)

# Consecutive checks with no giveaway badge before we consider it truly ended
ENDED_CONFIRM_CHECKS = 3


def rand(range_tuple):
    return random.uniform(range_tuple[0], range_tuple[1])


def sleep(range_tuple):
    duration = rand(range_tuple)
    time.sleep(duration)
    return duration


class WhatnotBot:
    def __init__(self):
        log.info("Connecting to device...")
        self.d = u2.connect_usb()
        log.info(f"Connected: {self.d.info.get('productName', 'Unknown')}")
        self.giveaways_entered = 0
        self.streams_checked = 0

    # ── Navigation ──

    def go_home(self):
        for _ in range(5):
            home_btn = self.d(resourceId="Home")
            if home_btn.exists:
                home_btn.click()
                sleep(ACTION_DELAY)
                log.info("Navigated to Home")
                return
            self.d.press("back")
            time.sleep(random.uniform(0.8, 1.5))
        log.warning("Could not get to Home screen")

    def go_to_category(self):
        cat = self.d(text=CATEGORY)
        if cat.exists:
            cat.click()
            time.sleep(random.uniform(3.0, 5.0))
            log.info(f"Tapped category: {CATEGORY}")
            return True
        log.warning(f"Category '{CATEGORY}' not found")
        return False

    def enter_first_stream(self):
        thumbnail = self.d(resourceId="show_item_thumbnail")
        if thumbnail.wait(timeout=10):
            thumbnail.click()
            time.sleep(random.uniform(2.0, 3.5))
            log.info("Entered first stream")
            return True
        for node in self.d.xpath("//*").all():
            text = node.info.get("text", "")
            if text.startswith("Live"):
                node.click()
                time.sleep(random.uniform(2.0, 3.5))
                log.info("Entered stream via Live badge")
                return True
        log.warning("No streams found after waiting")
        return False

    def scroll_to_next_stream(self):
        start_x = random.randint(400, 680)
        self.d.swipe(start_x, 2100, start_x, 200, duration=random.uniform(0.15, 0.3))
        time.sleep(random.uniform(1.5, 2.5))
        self.streams_checked += 1

    def leave_stream(self):
        leave_btn = self.d(description="Leave")
        if leave_btn.exists:
            leave_btn.click()
            sleep(ACTION_DELAY)
            log.info("Left stream")
            return
        self.d.press("back")
        sleep(ACTION_DELAY)
        log.info("Left stream via back")

    # ── Giveaway detection ──

    def has_giveaway(self):
        return self.d(text="Giveaway").exists

    def get_viewer_count(self):
        for node in self.d.xpath("//*").all():
            info = node.info
            text = info.get("text", "")
            bounds = info.get("bounds", {})
            if (text.isdigit()
                    and bounds.get("left", 0) > 700
                    and bounds.get("top", 0) < 300):
                return int(text)
        return None

    def get_streamer_name(self):
        for node in self.d.xpath("//*").all():
            info = node.info
            desc = info.get("contentDescription", "")
            bounds = info.get("bounds", {})
            if (desc and bounds.get("left", 0) < 200
                    and 80 < bounds.get("top", 0) < 300
                    and desc not in ("Leave", "Ship Time")):
                return desc
        return "unknown"

    def enter_giveaway(self):
        """Open giveaway panel and tap the entry button."""
        giveaway_el = self.d(text="Giveaway")
        if not giveaway_el.exists:
            return False

        giveaway_el.click()
        sleep(ENTRY_DELAY)

        entry_texts = [
            "Follow Host & Enter Giveaway",
            "Enter Giveaway",
            "Enter",
        ]
        for text in entry_texts:
            btn = self.d(text=text)
            if btn.exists:
                btn.click()
                self.giveaways_entered += 1
                log.info(f"ENTERED GIVEAWAY! (total: {self.giveaways_entered})")
                sleep(ACTION_DELAY)
                return True

        log.warning("No entry button found (maybe already entered?)")
        return False

    def is_giveaway_still_active(self):
        """Check if there's still an active giveaway badge on screen."""
        return self.d(text="Giveaway").exists or self.d(text="Entries").exists

    # ── Main logic ──

    def find_giveaway_stream(self):
        """Scroll through streams quickly looking for one with an active giveaway."""
        max_scrolls = 30

        for i in range(max_scrolls):
            name = self.get_streamer_name()
            viewers = self.get_viewer_count()
            has_gw = self.has_giveaway()

            log.info(f"Stream #{self.streams_checked}: {name} "
                     f"({viewers or '?'} viewers) "
                     f"{'GIVEAWAY!' if has_gw else 'no giveaway'}")

            if has_gw:
                if viewers is not None and viewers > MAX_VIEWERS:
                    log.info(f"Too many viewers ({viewers}), skipping...")
                    self.scroll_to_next_stream()
                    continue

                log.info(f"Found giveaway stream: {name}")
                return True

            self.scroll_to_next_stream()

        log.info("Checked many streams, refreshing...")
        return False

    def stay_for_giveaway(self):
        """
        Stay in the current stream until the giveaway fully runs its course.
        Checks every ~10s if the giveaway is still active.
        NEVER leaves while giveaway badge is showing.
        Once it ends, waits briefly for a new one.
        Returns when it's time to move on.
        """
        gone_count = 0
        start = time.time()

        # Phase 1: Wait for the current giveaway to finish
        # No hard timeout — if giveaway is active, we stay no matter what
        while True:
            sleep(GIVEAWAY_CHECK_INTERVAL)

            if self.is_giveaway_still_active():
                gone_count = 0
                elapsed = int(time.time() - start)
                log.info(f"Giveaway still active... ({elapsed}s elapsed)")
            else:
                gone_count += 1
                log.info(f"Giveaway badge gone (check {gone_count}/{ENDED_CONFIRM_CHECKS})")
                if gone_count >= ENDED_CONFIRM_CHECKS:
                    log.info("Giveaway confirmed ended.")
                    break

        # Phase 2: Giveaway ended — check viewers and wait for a new one
        viewers = self.get_viewer_count()
        name = self.get_streamer_name()
        log.info(f"Giveaway over in {name}. Viewers: {viewers or '?'}")

        if viewers is not None and viewers > MAX_VIEWERS:
            log.info(f"Viewers too high ({viewers}), moving on.")
            return

        # Wait a bit to see if a new giveaway starts
        log.info("Viewers still low, waiting to see if new giveaway starts...")
        wait_time = rand(NEW_GIVEAWAY_WAIT)
        wait_start = time.time()

        while time.time() - wait_start < wait_time:
            time.sleep(random.uniform(3, 6))

            if self.has_giveaway():
                log.info("Giveaway detected in this stream!")
                entered = self.enter_giveaway()
                if entered:
                    # Stay for this new giveaway too
                    self.stay_for_giveaway()
                else:
                    # Already entered (same giveaway still showing) — keep waiting
                    log.info("Already entered, staying to wait it out...")
                    self.stay_for_giveaway()
                return

        log.info("No new giveaway, moving on.")

    def run(self):
        log.info("=" * 50)
        log.info("Whatnot Giveaway Bot Starting")
        log.info(f"Max viewers: {MAX_VIEWERS} | Category: {CATEGORY}")
        log.info("=" * 50)

        try:
            self.go_home()
            sleep(ACTION_DELAY)

            if not self.go_to_category():
                log.error("Could not find category, aborting")
                return

            sleep(ACTION_DELAY)

            if not self.enter_first_stream():
                log.error("Could not enter a stream, aborting")
                return

            while True:
                # Scroll through streams looking for a giveaway
                found = self.find_giveaway_stream()

                if not found:
                    self.leave_stream()
                    sleep(TRANSITION_DELAY)
                    self.go_to_category()
                    sleep(ACTION_DELAY)
                    if not self.enter_first_stream():
                        log.error("Could not re-enter streams")
                        break
                    continue

                # Found a giveaway stream — enter it
                entered = self.enter_giveaway()

                if entered:
                    # STAY here until giveaway is done
                    self.stay_for_giveaway()

                # Move to next stream
                self.scroll_to_next_stream()

                log.info(f"Stats: {self.giveaways_entered} entered, "
                         f"{self.streams_checked} checked")

        except KeyboardInterrupt:
            log.info("\nBot stopped by user")
        except Exception as e:
            log.error(f"Error: {e}", exc_info=True)
        finally:
            log.info(f"\nFinal: {self.giveaways_entered} giveaways entered, "
                     f"{self.streams_checked} streams checked")


if __name__ == "__main__":
    bot = WhatnotBot()
    bot.run()
