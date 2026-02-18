"""
Whatnot Bot Web Dashboard — Flask server with API + SSE log streaming.
Run with: python server.py
"""

import collections
import json
import subprocess
import threading
import time

from flask import Flask, Response, jsonify, render_template, request

from config import DEFAULT_CONFIG

app = Flask(__name__)

# ── Shared state ──
bot_thread = None
bot_instance = None
stop_event = threading.Event()
log_deque = collections.deque(maxlen=2000)
current_config = dict(DEFAULT_CONFIG)


# ── Pages ──

@app.route("/")
def index():
    return render_template("dashboard.html")


# ── API ──

@app.route("/api/status")
def api_status():
    running = bot_thread is not None and bot_thread.is_alive()
    giveaways = bot_instance.giveaways_entered if bot_instance else 0
    streams = bot_instance.streams_checked if bot_instance else 0
    return jsonify({
        "running": running,
        "giveaways_entered": giveaways,
        "streams_checked": streams,
    })


@app.route("/api/start", methods=["POST"])
def api_start():
    global bot_thread, bot_instance, stop_event

    if bot_thread is not None and bot_thread.is_alive():
        return jsonify({"error": "Bot is already running"}), 400

    # Check for ADB device
    try:
        result = subprocess.run(
            ["adb", "devices"], capture_output=True, text=True, timeout=5
        )
        lines = [l for l in result.stdout.strip().split("\n")[1:] if l.strip()]
        if not lines:
            return jsonify({"error": "No ADB device connected"}), 400
    except Exception as e:
        return jsonify({"error": f"ADB check failed: {e}"}), 500

    # ADB setup: keep screen awake on USB
    try:
        subprocess.run(
            ["adb", "shell", "svc", "power", "stayon", "usb"],
            capture_output=True, timeout=5,
        )
        subprocess.run(
            ["adb", "shell", "settings", "put", "system",
             "screen_off_timeout", "2147483647"],
            capture_output=True, timeout=5,
        )
    except Exception:
        pass  # non-fatal

    stop_event = threading.Event()
    log_deque.clear()

    def run_bot():
        global bot_instance
        from bot import WhatnotBot
        try:
            bot_instance = WhatnotBot(
                config=dict(current_config),
                stop_event=stop_event,
                log_deque=log_deque,
            )
            bot_instance.run()
        except Exception as e:
            log_deque.append(f"SERVER ERROR: {e}")
        finally:
            bot_instance = None

    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    return jsonify({"ok": True})


@app.route("/api/stop", methods=["POST"])
def api_stop():
    global bot_thread
    if bot_thread is None or not bot_thread.is_alive():
        return jsonify({"error": "Bot is not running"}), 400

    stop_event.set()
    bot_thread.join(timeout=30)
    bot_thread = None
    return jsonify({"ok": True})


@app.route("/api/config")
def api_get_config():
    return jsonify(current_config)


@app.route("/api/config", methods=["POST"])
def api_set_config():
    if bot_thread is not None and bot_thread.is_alive():
        return jsonify({"error": "Cannot change config while bot is running"}), 400

    data = request.get_json(force=True)
    # Only update known keys with correct types
    int_keys = [
        "max_viewers_pack", "max_viewers_other",
        "max_wait_pack", "max_wait_other",
        "ended_checks_pack", "ended_checks_other",
    ]
    str_keys = ["mode", "category"]
    for k in int_keys:
        if k in data:
            try:
                current_config[k] = int(data[k])
            except (ValueError, TypeError):
                pass
    for k in str_keys:
        if k in data:
            current_config[k] = str(data[k])

    return jsonify(current_config)


@app.route("/api/logs")
def api_logs():
    """SSE endpoint — streams log lines from the shared deque."""
    def generate():
        idx = 0
        while True:
            while idx < len(log_deque):
                line = log_deque[idx]
                yield f"data: {json.dumps(line)}\n\n"
                idx += 1
            time.sleep(0.5)

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache",
                             "X-Accel-Buffering": "no"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=False)
