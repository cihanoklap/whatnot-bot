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
import threading
import collections
from config import (
    DEFAULT_CONFIG,
    POLL_INTERVAL, NO_GIVEAWAY_TIMEOUT,
    ACTION_DELAY, ENTRY_DELAY, TRANSITION_DELAY,
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
NEW_GIVEAWAY_WAIT = (45, 60)

# Log file for giveaway history
LOG_FILE = os.path.join(os.path.dirname(__file__), "giveaway_log.csv")


class DequeLogHandler(logging.Handler):
    """Pushes formatted log lines to a shared deque for SSE streaming."""

    def __init__(self, deque):
        super().__init__()
        self.deque = deque

    def emit(self, record):
        try:
            self.deque.append(self.format(record))
        except Exception:
            pass


def rand(range_tuple):
    return random.uniform(range_tuple[0], range_tuple[1])


def sleep(range_tuple):
    duration = rand(range_tuple)
    time.sleep(duration)
    return duration


class WhatnotBot:
    def __init__(self, config=None, stop_event=None, log_deque=None):
        # Merge provided config over defaults
        self.cfg = dict(DEFAULT_CONFIG)
        if config:
            self.cfg.update(config)

        self.stop_event = stop_event or threading.Event()

        # Attach deque log handler if provided
        if log_deque is not None:
            handler = DequeLogHandler(log_deque)
            handler.setFormatter(logging.Formatter(
                "%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S"
            ))
            log.addHandler(handler)
            self._deque_handler = handler
        else:
            self._deque_handler = None

        log.info("Connecting to device...")
        self.d = u2.connect_usb()
        log.info(f"Connected: {self.d.info.get('productName', 'Unknown')}")
        self.giveaways_entered = 0
        self.streams_checked = 0
        self._init_log()

    def _stopped(self):
        """Check if the stop event has been set."""
        return self.stop_event.is_set()

    def cleanup(self):
        """Remove the deque log handler when done."""
        if self._deque_handler:
            log.removeHandler(self._deque_handler)
            self._deque_handler = None

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

    def _find_and_click_home(self):
        """Try multiple selectors to find and click the Home button."""
        for selector in [
            self.d(resourceId="Home"),
            self.d(description="Home"),
            self.d(text="Home"),
        ]:
            if selector.exists:
                selector.click()
                sleep(ACTION_DELAY)
                return True
        return False

    def go_home(self):
        # Try pressing back to exit any screens
        for _ in range(5):
            if self._stopped():
                return False
            if self._find_and_click_home():
                log.info("Navigated to Home")
                return True
            self.d.press("back")
            time.sleep(random.uniform(0.8, 1.5))
        # Fallback: press the Android home button and re-open app
        self.d.press("home")
        time.sleep(random.uniform(1.5, 2.5))
        self.d.app_start("com.whatnot.whatnot")
        time.sleep(random.uniform(4.0, 6.0))
        if self._find_and_click_home():
            log.info("Navigated to Home (via app restart)")
            return True
        # Last resort: try pressing back a few more times after app restart
        for _ in range(3):
            if self._stopped():
                return False
            self.d.press("back")
            time.sleep(random.uniform(0.8, 1.5))
            if self._find_and_click_home():
                log.info("Navigated to Home (after back)")
                return True
        log.warning("Could not get to Home screen")
        return False

    def go_to_category(self, use_followed=False):
        """
        Navigate to a category on the Home screen.

        Normal mode:
          use_followed=False: Pokémon Cards → New And Noteworthy tab
          use_followed=True:  Followed Hosts (separate category)

        Lowest-viewer mode:
          use_followed=False: Pokémon Cards → sort by viewer count
          use_followed=True:  Followed Hosts (same as normal)
        """
        category = self.cfg["category"]
        mode = self.cfg["mode"]

        if use_followed:
            cat = self.d(text="Followed Hosts")
            if cat.exists:
                cat.click()
                time.sleep(random.uniform(3.0, 5.0))
                log.info("Tapped category: Followed Hosts")
                return True
            log.warning("'Followed Hosts' category not found")
            return False

        cat = self.d(text=category)
        if cat.exists:
            cat.click()
            time.sleep(random.uniform(3.0, 5.0))
            log.info(f"Tapped category: {category}")

            if mode == "lowest_viewer":
                # Tap Filter button (identified by contentDescription)
                filter_btn = self.d(description="Filter")
                if not filter_btn.exists:
                    filter_btn = self.d(text="Filter")
                if filter_btn.exists:
                    filter_btn.click()
                    time.sleep(random.uniform(2.0, 3.5))
                    log.info("Opened Filter panel")

                    # Look for viewer-count sort inside filter panel
                    # The text label isn't clickable — the checkbox/radio
                    # next to it is. Find the label, get its bounds, then
                    # click the clickable element to its left.
                    sort_selected = False
                    for viewer_opt in ["Viewers: low to high",
                                       "Viewers: Low to High",
                                       "Viewers: low",
                                       "Low to High"]:
                        opt = self.d(textContains=viewer_opt)
                        if opt.exists:
                            bounds = opt.info.get("bounds", {})
                            cy = (bounds.get("top", 0) + bounds.get("bottom", 0)) // 2
                            # Click to the left of the label where the
                            # radio/checkbox sits
                            cx = max(bounds.get("left", 60) - 40, 30)
                            self.d.click(cx, cy)
                            time.sleep(random.uniform(1.5, 2.5))
                            log.info(f"Selected sort: {viewer_opt} (clicked at {cx},{cy})")
                            sort_selected = True
                            break
                    if not sort_selected:
                        log.warning("Viewer sort not found in filter panel")

                    # Apply / close filter if there's an apply button
                    for apply_text in ["Apply", "Show Results", "Done"]:
                        apply_btn = self.d(text=apply_text)
                        if apply_btn.exists:
                            apply_btn.click()
                            time.sleep(random.uniform(2.0, 3.5))
                            log.info(f"Applied filter ({apply_text})")
                            break
                    else:
                        # Close panel if no apply button
                        self.d.press("back")
                        time.sleep(random.uniform(1.0, 2.0))
                else:
                    log.warning("Filter button not found, "
                                "falling back to New And Noteworthy")
                    tab = self.d(text="New And Noteworthy")
                    tab.wait(timeout=5)
                    if tab.exists:
                        tab.click()
                        time.sleep(random.uniform(2.0, 3.5))
                        log.info("Switched to New And Noteworthy (fallback)")
            else:
                # Normal mode: use New And Noteworthy
                tab = self.d(text="New And Noteworthy")
                tab.wait(timeout=5)
                if tab.exists:
                    tab.click()
                    time.sleep(random.uniform(2.0, 3.5))
                    log.info("Switched to New And Noteworthy")
                else:
                    log.warning("'New And Noteworthy' tab not found")
            return True
        log.warning(f"Category '{category}' not found")
        return False

    def enter_first_stream(self):
        for attempt in range(3):
            if self._stopped():
                return False
            thumbnail = self.d(resourceId="show_item_thumbnail")
            if thumbnail.wait(timeout=10):
                try:
                    thumbnail.click()
                    time.sleep(random.uniform(2.0, 3.5))
                    log.info("Entered first stream")
                    return True
                except Exception:
                    log.warning(f"Stale thumbnail, retrying ({attempt + 1}/3)...")
                    time.sleep(random.uniform(1.0, 2.0))
                    continue
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

    @staticmethod
    def _parse_viewer_text(text):
        """Parse viewer count strings like '5', '1.3k', '1.3K', '12K'."""
        text = text.strip().lower()
        if text.endswith("k"):
            try:
                return int(float(text[:-1]) * 1000)
            except ValueError:
                return None
        if text.isdigit():
            return int(text)
        return None

    def get_viewer_count(self):
        for attempt in range(2):
            for node in self.d.xpath("//*").all():
                info = node.info
                text = info.get("text", "")
                bounds = info.get("bounds", {})
                if (bounds.get("left", 0) > 700
                        and bounds.get("top", 0) < 300):
                    count = self._parse_viewer_text(text)
                    if count is not None:
                        return count
            if attempt == 0:
                time.sleep(1.5)  # wait for UI to load, retry
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
        for node in self.d.xpath("//*").all():
            info = node.info
            text = info.get("text", "").lower()
            bounds = info.get("bounds", {})
            if bounds.get("top", 0) < 400 and "pack" in text:
                return True
        return False

    def enter_giveaway(self, viewers=None):
        """
        Open giveaway panel, check type, apply viewer limits, enter.
        Returns (entered, is_pack, skipped).
        """
        max_viewers_other = self.cfg["max_viewers_other"]

        giveaway_el = self.d(text="Giveaway")
        if not giveaway_el.exists:
            return False, False, False

        try:
            giveaway_el.click()
        except Exception:
            log.warning("Giveaway badge went stale, skipping...")
            return False, False, False
        sleep(ENTRY_DELAY)

        is_pack = self.check_is_pack_giveaway()
        giveaway_type = "PACK" if is_pack else "other"

        # Check viewer limit BEFORE entering
        if not is_pack and viewers is not None and viewers > max_viewers_other:
            log.info(f"Non-pack giveaway with {viewers} viewers (>{max_viewers_other}), skipping...")
            self._close_giveaway_panel()
            return False, is_pack, True

        entry_texts = [
            "Follow Host & Enter Giveaway",
            "Enter Giveaway",
            "Enter",
        ]
        for text in entry_texts:
            btn = self.d(text=text)
            if btn.exists:
                try:
                    btn.click()
                except Exception:
                    log.warning("Entry button went stale, retrying...")
                    continue
                self.giveaways_entered += 1
                log.info(f"ENTERED {giveaway_type} GIVEAWAY! (total: {self.giveaways_entered})")
                sleep(ACTION_DELAY)
                return True, is_pack, False

        log.warning("No entry button found (maybe already entered?)")
        self._close_giveaway_panel()
        return False, is_pack, False

    def is_giveaway_still_active(self):
        return self.d(text="Giveaway").exists or self.d(text="Entries").exists

    def _close_giveaway_panel(self):
        """Close the giveaway panel using the Close button (top-right)."""
        try:
            close_btn = self.d(description="Close")
            if close_btn.exists:
                close_btn.click()
            else:
                self.d.press("back")
        except Exception:
            self.d.press("back")
        time.sleep(random.uniform(0.5, 1.0))

    # ── Main logic ──

    def find_giveaway_stream(self):
        """
        Scroll through streams looking for one with an active giveaway.
        Detects when stuck on the same stream and bails early.
        """
        max_viewers_pack = self.cfg["max_viewers_pack"]
        max_scrolls = 30
        last_name = None
        stuck_count = 0

        for i in range(max_scrolls):
            if self._stopped():
                return False, None

            name = self.get_streamer_name()
            viewers = self.get_viewer_count()
            has_gw = self.has_giveaway()

            log.info(f"Stream #{self.streams_checked}: {name} "
                     f"({viewers or '?'} viewers) "
                     f"{'GIVEAWAY!' if has_gw else 'no giveaway'}")

            # Stuck detection — same name means swipe didn't move
            if name == last_name:
                stuck_count += 1
                if stuck_count >= 3:
                    log.info(f"Stuck on {name} for {stuck_count} scrolls, refreshing...")
                    return False, None
            else:
                stuck_count = 0
            last_name = name

            if has_gw:
                if viewers is not None and viewers > max_viewers_pack:
                    log.info(f"Too many viewers ({viewers}), skipping...")
                    self.scroll_to_next_stream()
                    continue

                log.info(f"Found giveaway stream: {name}")
                return True, viewers

            self.scroll_to_next_stream()

        log.info("Checked many streams, refreshing...")
        return False, None

    def find_giveaway_stream_grid(self):
        """
        Grid-based stream finder for lowest_viewer mode.
        Clicks each thumbnail from the category grid, checks for giveaway
        inside the stream, and goes back if none found.
        Returns (found, viewers) — when found=True the bot is inside the stream.
        """
        max_viewers_pack = self.cfg["max_viewers_pack"]
        max_checks = 30
        checked = 0
        stale_scrolls = 0

        while checked < max_checks:
            if self._stopped():
                return False, None

            thumbnails = self.d(resourceId="show_item_thumbnail")
            if not thumbnails.wait(timeout=10):
                log.info("No thumbnails visible on grid after waiting 10s")
                return False, None
            count = thumbnails.count

            if count == 0:
                log.info("No thumbnails visible on grid")
                return False, None

            for i in range(count):
                if self._stopped():
                    return False, None
                if checked >= max_checks:
                    break

                # Re-fetch thumbnails in case UI shifted
                thumbnails = self.d(resourceId="show_item_thumbnail")
                if i >= thumbnails.count:
                    break

                try:
                    thumbnails[i].click()
                except Exception:
                    log.warning(f"Stale thumbnail at index {i}, skipping")
                    continue
                time.sleep(random.uniform(2.0, 3.5))

                self.streams_checked += 1
                checked += 1

                name = self.get_streamer_name()
                viewers = self.get_viewer_count()
                has_gw = self.has_giveaway()

                log.info(f"Stream #{self.streams_checked}: {name} "
                         f"({viewers or '?'} viewers) "
                         f"{'GIVEAWAY!' if has_gw else 'no giveaway'}")

                if has_gw:
                    if viewers is not None and viewers > max_viewers_pack:
                        log.info(f"Too many viewers ({viewers}), skipping...")
                        self.leave_stream()
                        time.sleep(random.uniform(1.5, 2.5))
                        continue

                    log.info(f"Found giveaway stream: {name}")
                    return True, viewers

                # No giveaway — go back to grid
                self.leave_stream()
                time.sleep(random.uniform(1.5, 2.5))

            # Scroll grid down to load more thumbnails
            self.d.swipe(540, 1800, 540, 600, duration=random.uniform(0.3, 0.5))
            time.sleep(random.uniform(2.0, 3.5))

            new_count = self.d(resourceId="show_item_thumbnail").count
            if new_count == 0:
                stale_scrolls += 1
            else:
                stale_scrolls = 0

            if stale_scrolls >= 2:
                log.info("No more streams to load, refreshing...")
                return False, None

        log.info("Checked many streams from grid, refreshing...")
        return False, None

    def check_can_enter_again(self):
        """Click giveaway badge to check if a new giveaway started."""
        giveaway_el = self.d(text="Giveaway")
        if not giveaway_el.exists:
            return False, False

        try:
            giveaway_el.click()
        except Exception:
            log.warning("Giveaway badge went stale during check")
            return False, False
        time.sleep(random.uniform(1.0, 1.5))

        is_pack = self.check_is_pack_giveaway()

        entry_texts = [
            "Follow Host & Enter Giveaway",
            "Enter Giveaway",
            "Enter",
        ]
        for text in entry_texts:
            btn = self.d(text=text)
            if btn.exists:
                log.info(f"New giveaway available! ({'pack' if is_pack else 'other'})")
                return True, is_pack

        self._close_giveaway_panel()
        return False, False

    def stay_for_giveaway(self, is_pack):
        """
        Stay until giveaway ends or max wait hit.
        Two check mechanisms:
          1. Passive (every 8-13s): read badge text without clicking
          2. Active (every ~20s): click badge, check if we can enter again
        Returns (wait_seconds, capped, new_is_pack).
        """
        max_wait = self.cfg["max_wait_pack"] if is_pack else self.cfg["max_wait_other"]
        ended_checks = self.cfg["ended_checks_pack"] if is_pack else self.cfg["ended_checks_other"]
        giveaway_type = "pack" if is_pack else "other"
        start = time.time()
        capped = False
        gone_count = 0
        last_active_check = time.time()
        ACTIVE_CHECK_INTERVAL = 20  # seconds between active checks

        log.info(f"Staying for {giveaway_type} giveaway (max {max_wait // 60}min, "
                 f"{ended_checks} confirm checks)...")

        while True:
            if self._stopped():
                wait_seconds = time.time() - start
                return wait_seconds, False, None

            sleep(GIVEAWAY_CHECK_INTERVAL)
            elapsed = time.time() - start

            if elapsed >= max_wait:
                log.info(f"Max wait reached ({max_wait // 60}min), moving on.")
                capped = True
                break

            # Active check: click badge every ~20s to verify we're still entered
            if time.time() - last_active_check >= ACTIVE_CHECK_INTERVAL:
                last_active_check = time.time()
                if self.has_giveaway():
                    new_available, new_is_pack = self.check_can_enter_again()
                    if new_available:
                        wait_seconds = time.time() - start
                        return wait_seconds, False, new_is_pack
                    gone_count = 0
                    log.info(f"Still entered, giveaway active ({int(elapsed)}s elapsed)")
                    continue
                else:
                    gone_count += 1
                    log.info(f"Giveaway badge gone (check {gone_count}/{ended_checks})")
                    if gone_count >= ended_checks:
                        log.info("Giveaway confirmed ended.")
                        break
                    continue

            # Passive check: just read badge text without clicking
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
        return wait_seconds, capped, None

    # ── Giveaway stay + enter helpers ──

    def _handle_giveaway_in_stream(self, viewers):
        """
        Shared logic for both modes: enter giveaway, stay, handle re-entries.
        Bot must already be inside the stream. Returns when done with this stream.
        """
        entered, is_pack, skipped = self.enter_giveaway(viewers=viewers)

        if skipped:
            log.info(f"Stats: {self.giveaways_entered} entered, "
                     f"{self.streams_checked} checked")
            return "skipped"

        if not entered:
            if not self.is_giveaway_still_active():
                log.info("Giveaway already ended, moving on.")
                log.info(f"Stats: {self.giveaways_entered} entered, "
                         f"{self.streams_checked} checked")
                return "ended"
            log.info("Already entered this giveaway, staying to wait it out...")

        streamer = self.get_streamer_name()
        current_is_pack = is_pack

        while not self._stopped():
            wait_seconds, capped, new_is_pack = self.stay_for_giveaway(current_is_pack)

            current_viewers = self.get_viewer_count()
            self._log_giveaway(streamer, current_is_pack, wait_seconds, capped, current_viewers)

            if self._stopped():
                break

            if new_is_pack is not None:
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
                        gw_type = "PACK" if new_is_pack else "other"
                        log.info(f"ENTERED {gw_type} GIVEAWAY! (total: {self.giveaways_entered})")
                        sleep(ACTION_DELAY)
                        break
                current_is_pack = new_is_pack
                continue

            max_viewers = self.cfg["max_viewers_pack"] if current_is_pack else self.cfg["max_viewers_other"]
            if capped or (current_viewers is not None and current_viewers > max_viewers):
                log.info("Moving on from this stream.")
                break

            log.info("Waiting to see if new giveaway starts...")
            wait_start = time.time()
            wait_time = rand(NEW_GIVEAWAY_WAIT)
            found_new = False

            while time.time() - wait_start < wait_time:
                if self._stopped():
                    break
                time.sleep(random.uniform(3, 6))
                if self.has_giveaway():
                    new_available, new_pk = self.check_can_enter_again()
                    if new_available:
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
                                gw_type = "PACK" if new_pk else "other"
                                log.info(f"ENTERED {gw_type} GIVEAWAY! (total: {self.giveaways_entered})")
                                sleep(ACTION_DELAY)
                                break
                        current_is_pack = new_pk
                        found_new = True
                        break

            if self._stopped():
                break

            if not found_new:
                log.info("No new giveaway, done with this stream.")
                break

        log.info("Done with this stream.")
        log.info(f"Stats: {self.giveaways_entered} entered, "
                 f"{self.streams_checked} checked")
        return "done"

    # ── Run modes ──

    def _run_normal(self, mode):
        """Normal mode: enter first stream, swipe through to find giveaways."""
        if self._stopped():
            return
        if not self.enter_first_stream():
            log.error("Could not enter a stream, aborting")
            return

        use_followed = False
        while not self._stopped():
            found, viewers = self.find_giveaway_stream()

            if self._stopped():
                break

            if not found:
                self.leave_stream()
                sleep(TRANSITION_DELAY)
                use_followed = not use_followed
                if use_followed:
                    log.info("Falling back to Followed Hosts...")
                else:
                    log.info("Switching back to New And Noteworthy...")
                # Keep retrying until we get back in
                for attempt in range(5):
                    if self._stopped():
                        break
                    self.go_home()
                    sleep(ACTION_DELAY)
                    self.go_to_category(use_followed=use_followed)
                    sleep(ACTION_DELAY)
                    if self.enter_first_stream():
                        break
                    log.warning(f"Could not re-enter streams (attempt {attempt + 1}/5), waiting...")
                    time.sleep(random.uniform(5, 10))
                else:
                    if self._stopped():
                        break
                    log.warning("All 5 attempts failed, trying other category...")
                    use_followed = not use_followed
                    self.go_home()
                    sleep(ACTION_DELAY)
                    self.go_to_category(use_followed=use_followed)
                    sleep(ACTION_DELAY)
                    if not self.enter_first_stream():
                        log.warning("Still can't enter, waiting 30s and retrying...")
                        time.sleep(30)
                        continue
                continue

            result = self._handle_giveaway_in_stream(viewers)

            if result == "skipped" or result == "ended":
                self.scroll_to_next_stream()
                continue

            # "done" — finished with giveaway, move to next stream
            self.scroll_to_next_stream()

    def _run_lowest_viewer(self, mode):
        """Lowest-viewer mode: stay on grid, click thumbnails one by one."""
        use_followed = False
        while not self._stopped():
            found, viewers = self.find_giveaway_stream_grid()

            if self._stopped():
                break

            if not found:
                sleep(TRANSITION_DELAY)
                use_followed = not use_followed
                if use_followed:
                    log.info("Falling back to Followed Hosts...")
                else:
                    log.info("Switching back to viewer-count sort...")
                for attempt in range(5):
                    if self._stopped():
                        break
                    self.go_home()
                    sleep(ACTION_DELAY)
                    self.go_to_category(use_followed=use_followed)
                    sleep(ACTION_DELAY)
                    # Grid mode — just need category to load, check thumbnails
                    thumbnails = self.d(resourceId="show_item_thumbnail")
                    if thumbnails.wait(timeout=10) and thumbnails.count > 0:
                        break
                    log.warning(f"No streams on grid (attempt {attempt + 1}/5), waiting...")
                    time.sleep(random.uniform(5, 10))
                else:
                    if self._stopped():
                        break
                    log.warning("All 5 attempts failed, trying other category...")
                    use_followed = not use_followed
                    self.go_home()
                    sleep(ACTION_DELAY)
                    self.go_to_category(use_followed=use_followed)
                    sleep(ACTION_DELAY)
                    thumbnails = self.d(resourceId="show_item_thumbnail")
                    if not (thumbnails.wait(timeout=10) and thumbnails.count > 0):
                        log.warning("Still no streams, waiting 30s and retrying...")
                        time.sleep(30)
                        continue
                continue

            # Bot is inside the giveaway stream
            self._handle_giveaway_in_stream(viewers)

            # Go back to grid
            self.leave_stream()
            time.sleep(random.uniform(1.5, 2.5))

    def run(self):
        max_viewers_pack = self.cfg["max_viewers_pack"]
        max_viewers_other = self.cfg["max_viewers_other"]
        max_wait_pack = self.cfg["max_wait_pack"]
        max_wait_other = self.cfg["max_wait_other"]
        category = self.cfg["category"]
        mode = self.cfg["mode"]

        log.info("=" * 50)
        log.info("Whatnot Giveaway Bot Starting")
        log.info(f"Mode: {mode}")
        log.info(f"Pack: ≤{max_viewers_pack} viewers, {max_wait_pack // 60}min max")
        log.info(f"Other: ≤{max_viewers_other} viewers, {max_wait_other // 60}min max")
        log.info(f"Category: {category}")
        log.info("=" * 50)

        try:
            if self._stopped():
                return
            self.go_home()
            sleep(ACTION_DELAY)

            if self._stopped():
                return
            if not self.go_to_category():
                log.error("Could not find category, aborting")
                return

            sleep(ACTION_DELAY)

            if mode == "lowest_viewer":
                self._run_lowest_viewer(mode)
            else:
                self._run_normal(mode)

        except KeyboardInterrupt:
            log.info("\nBot stopped by user")
        except Exception as e:
            log.error(f"Error: {e}", exc_info=True)
        finally:
            log.info(f"\nFinal: {self.giveaways_entered} giveaways entered, "
                     f"{self.streams_checked} streams checked")
            log.info(f"Giveaway log saved to: {LOG_FILE}")
            self.cleanup()


if __name__ == "__main__":
    bot = WhatnotBot()
    bot.run()
