"""
Quick navigation + capture helper.
Usage:
    python navigate.py tap_pokemon    - Tap the Pokemon Cards category
    python navigate.py tap_stream N   - Tap the Nth stream thumbnail (0-indexed)
    python navigate.py back           - Press back button
    python navigate.py capture NAME   - Just capture current screen
    python navigate.py scroll         - Scroll down
"""

import uiautomator2 as u2
import sys
import os
import time
import json

DISCOVERY_DIR = os.path.join(os.path.dirname(__file__), "discovery")


def connect():
    d = u2.connect_usb()
    print(f"Connected: {d.info.get('productName', 'Unknown')}")
    return d


def capture(d, name):
    os.makedirs(DISCOVERY_DIR, exist_ok=True)
    ts = int(time.time())
    prefix = f"{name}_{ts}"

    ss_path = os.path.join(DISCOVERY_DIR, f"{prefix}.png")
    d.screenshot(ss_path)

    xml_path = os.path.join(DISCOVERY_DIR, f"{prefix}.xml")
    xml = d.dump_hierarchy()
    with open(xml_path, "w") as f:
        f.write(xml)

    elements = []
    for node in d.xpath("//*").all():
        info = node.info
        if info.get("text") or info.get("contentDescription") or info.get("clickable"):
            elements.append({
                "text": info.get("text", ""),
                "content_desc": info.get("contentDescription", ""),
                "class": info.get("className", ""),
                "resource_id": info.get("resourceName", ""),
                "clickable": info.get("clickable", False),
                "bounds": info.get("bounds", {}),
            })

    json_path = os.path.join(DISCOVERY_DIR, f"{prefix}_elements.json")
    with open(json_path, "w") as f:
        json.dump(elements, f, indent=2)

    print(f"Captured '{name}': {ss_path} ({len(elements)} elements)")
    for el in elements[:30]:
        text = el["text"] or el["content_desc"] or el["resource_id"]
        if text:
            click = " [clickable]" if el["clickable"] else ""
            print(f"  - {text}{click}")
    if len(elements) > 30:
        print(f"  ... and {len(elements) - 30} more")
    return elements


def main():
    if len(sys.argv) < 2:
        print("Usage: python navigate.py <command> [args]")
        return

    d = connect()
    cmd = sys.argv[1]

    if cmd == "tap_pokemon":
        # Tap the Pokemon Cards category pill
        el = d(text="Pokémon Cards")
        if el.exists:
            el.click()
            print("Tapped 'Pokémon Cards'")
            time.sleep(2)
            capture(d, "pokemon_category")
        else:
            print("Could not find 'Pokémon Cards' element")

    elif cmd == "tap_stream":
        idx = int(sys.argv[2]) if len(sys.argv) > 2 else 0
        thumbnails = d(resourceId="show_item_thumbnail")
        count = thumbnails.count
        print(f"Found {count} stream thumbnails")
        if idx < count:
            thumbnails[idx].click()
            print(f"Tapped stream #{idx}")
            time.sleep(3)
            capture(d, f"stream_{idx}")
        else:
            print(f"Index {idx} out of range (max {count - 1})")

    elif cmd == "back":
        d.press("back")
        print("Pressed back")
        time.sleep(1)
        capture(d, "after_back")

    elif cmd == "capture":
        name = sys.argv[2] if len(sys.argv) > 2 else "screen"
        capture(d, name)

    elif cmd == "scroll":
        d.swipe(540, 1800, 540, 600, duration=0.5)
        print("Scrolled down")
        time.sleep(1)
        capture(d, "after_scroll")

    else:
        print(f"Unknown command: {cmd}")


if __name__ == "__main__":
    main()
