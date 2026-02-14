"""
Whatnot Giveaway Bot
Finds low-viewer Pokemon card streams, enters giveaways,
waits for results, and moves on.
"""

import uiautomator2 as u2
import time
import random
import csv
import os
import logging
from config import (
    MAX_VIEWERS_PACK, MAX_VIEWERS_OTHER,
    MAX_WAIT_PACK, MAX_WAIT_OTHER,
    ENDED_CHECKS_PACK, ENDED_CHECKS_OTHER,
    POLL_INTERVAL, NO_GIVEAWAY_TIMEOUT,
    ACTION_DELAY, ENTRY_DELAY, TRANSITION_DELAY, CATEGORY,
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

# Log file for giveaway history
LOG_FILE = os.path.join(os.path.dirname(__file__), "giveaway_log.csv")


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
        self._init_log()

    def _init_log(self):
        """Create CSV log file with headers if it doesn't exist."""
        if not os.path.exists(LOG_FILE):
            with open(LOG_FILE, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["timestamp", "streamer", "is_pack", "wait_time", "viewers"])

    def _log_giveaway(self, streamer, is_pack, wait_seconds, capped, viewers):
        """Append a giveaway entry to the CSV log."""
        wait_str = f"{int(wait_seconds)}+" if capped else str(int(wait_seconds))
        pack_str = "pack" if is_pack else "other"
        with open(LOG_FILE, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                time.strftime("%Y-%m-%d %H:%M:%S"),
                streamer,
                pack_str,
                wait_str,
                viewers or "?",
            ])
        log.info(f"Logged: {streamer} | {pack_str} | {wait_str}s | {viewers or '?'} viewers")

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

    def check_is_pack_giveaway(self):
        """
        After tapping the Giveaway button, read the giveaway description
        text to check if it contains 'pack'.
        """
        for node in self.d.xpath("//*").all():
            info = node.info
            text = info.get("text", "").lower()
            bounds = info.get("bounds", {})
            # Giveaway title/description is in the top area of the panel
            if bounds.get("top", 0) < 400 and "pack" in text:
                return True
        return False

    def enter_giveaway(self):
        """
        Open giveaway panel, check if it's a pack giveaway,
        and tap the entry button.
        Returns (entered: bool, is_pack: bool).
        """
        giveaway_el = self.d(text="Giveaway")
        if not giveaway_el.exists:
            return False, False

        giveaway_el.click()
        sleep(ENTRY_DELAY)

        # Check if it's a pack giveaway before entering
        is_pack = self.check_is_pack_giveaway()
        giveaway_type = "PACK" if is_pack else "other"

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
                log.info(f"ENTERED {giveaway_type} GIVEAWAY! (total: {self.giveaways_entered})")
                sleep(ACTION_DELAY)
                return True, is_pack

        log.warning("No entry button found (maybe already entered?)")
        return False, is_pack

    def is_giveaway_still_active(self):
        return self.d(text="Giveaway").exists or self.d(text="Entries").exists

    # ── Main logic ──

    def find_giveaway_stream(self):
        """
        Scroll through streams looking for one with an active giveaway.
        Applies viewer limits: enters any giveaway stream ≤50 viewers,
        but will later filter non-pack giveaways by the stricter limit.
        """
        max_scrolls = 30

        for i in range(max_scrolls):
            name = self.get_streamer_name()
            viewers = self.get_viewer_count()
            has_gw = self.has_giveaway()

            log.info(f"Stream #{self.streams_checked}: {name} "
                     f"({viewers or '?'} viewers) "
                     f"{'GIVEAWAY!' if has_gw else 'no giveaway'}")

            if has_gw:
                # Use the higher limit here — we'll check pack status after opening
                if viewers is not None and viewers > MAX_VIEWERS_PACK:
                    log.info(f"Too many viewers ({viewers}), skipping...")
                    self.scroll_to_next_stream()
                    continue

                log.info(f"Found giveaway stream: {name}")
                return True, viewers

            self.scroll_to_next_stream()

        log.info("Checked many streams, refreshing...")
        return False, None

    def stay_for_giveaway(self, is_pack):
        """
        Stay in the current stream until the giveaway ends or max wait is hit.
        Returns (wait_seconds, capped).
        """
        max_wait = MAX_WAIT_PACK if is_pack else MAX_WAIT_OTHER
        ended_checks = ENDED_CHECKS_PACK if is_pack else ENDED_CHECKS_OTHER
        giveaway_type = "pack" if is_pack else "other"
        gone_count = 0
        start = time.time()
        capped = False

        log.info(f"Staying for {giveaway_type} giveaway (max {max_wait // 60}min, "
                 f"{ended_checks} confirm checks)...")

        while True:
            sleep(GIVEAWAY_CHECK_INTERVAL)
            elapsed = time.time() - start

            # Check max wait cap
            if elapsed >= max_wait:
                log.info(f"Max wait reached ({max_wait // 60}min), moving on.")
                capped = True
                break

            if self.is_giveaway_still_active():
                gone_count = 0
                log.info(f"Giveaway still active... ({int(elapsed)}s elapsed)")
            else:
                gone_count += 1
                log.info(f"Giveaway badge gone (check {gone_count}/{ended_checks})")
                if gone_count >= ended_checks:
                    log.info("Giveaway confirmed ended.")
                    break

        wait_seconds = time.time() - start
        return wait_seconds, capped

    def run(self):
        log.info("=" * 50)
        log.info("Whatnot Giveaway Bot Starting")
        log.info(f"Pack: ≤{MAX_VIEWERS_PACK} viewers, {MAX_WAIT_PACK // 60}min max")
        log.info(f"Other: ≤{MAX_VIEWERS_OTHER} viewers, {MAX_WAIT_OTHER // 60}min max")
        log.info(f"Category: {CATEGORY}")
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
                found, viewers = self.find_giveaway_stream()

                if not found:
                    self.leave_stream()
                    sleep(TRANSITION_DELAY)
                    self.go_to_category()
                    sleep(ACTION_DELAY)
                    if not self.enter_first_stream():
                        log.error("Could not re-enter streams")
                        break
                    continue

                # Open giveaway panel and check type
                entered, is_pack = self.enter_giveaway()

                if entered:
                    # Apply stricter viewer limit for non-pack giveaways
                    if not is_pack and viewers is not None and viewers > MAX_VIEWERS_OTHER:
                        log.info(f"Non-pack giveaway with {viewers} viewers (>{MAX_VIEWERS_OTHER}), skipping...")
                        self.scroll_to_next_stream()
                        log.info(f"Stats: {self.giveaways_entered} entered, "
                                 f"{self.streams_checked} checked")
                        continue

                    streamer = self.get_streamer_name()

                    # Stay for giveaway
                    wait_seconds, capped = self.stay_for_giveaway(is_pack)

                    # Log it
                    current_viewers = self.get_viewer_count()
                    self._log_giveaway(streamer, is_pack, wait_seconds, capped, current_viewers)

                    # Check if we should stay for more
                    max_viewers = MAX_VIEWERS_PACK if is_pack else MAX_VIEWERS_OTHER
                    if current_viewers is not None and current_viewers <= max_viewers and not capped:
                        log.info("Viewers still low, waiting for new giveaway...")
                        wait_start = time.time()
                        wait_time = rand(NEW_GIVEAWAY_WAIT)

                        while time.time() - wait_start < wait_time:
                            time.sleep(random.uniform(3, 6))

                            if self.has_giveaway():
                                log.info("Giveaway detected in this stream!")
                                entered2, is_pack2 = self.enter_giveaway()
                                if entered2:
                                    wait2, capped2 = self.stay_for_giveaway(is_pack2)
                                    self._log_giveaway(streamer, is_pack2, wait2, capped2,
                                                       self.get_viewer_count())
                                elif is_pack2 or self.is_giveaway_still_active():
                                    # Already entered same giveaway, wait it out
                                    log.info("Already entered, staying...")
                                    wait2, capped2 = self.stay_for_giveaway(is_pack2)
                                    self._log_giveaway(streamer, is_pack2, wait2, capped2,
                                                       self.get_viewer_count())
                                break

                        log.info("Done with this stream.")

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
            log.info(f"Giveaway log saved to: {LOG_FILE}")


if __name__ == "__main__":
    bot = WhatnotBot()
    bot.run()
