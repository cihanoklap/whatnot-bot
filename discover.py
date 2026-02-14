"""
UI Discovery Script for Whatnot App
Auto-captures UI hierarchy and screenshots with sequential naming.

Usage:
    # Capture current screen with auto-generated name
    python discover.py

    # Capture with a specific name
    python discover.py home
    python discover.py browse
    python discover.py stream
    python discover.py giveaway

Each run captures one screen. Navigate in the app, then run again.
Outputs saved to ./discovery/ folder.
"""

import uiautomator2 as u2
import os
import sys
import time
import json

DISCOVERY_DIR = os.path.join(os.path.dirname(__file__), "discovery")


def connect_device():
    d = u2.connect_usb()
    info = d.info
    print(f"Connected: {info.get('productName', 'Unknown')}")
    return d


def dump_screen(d, name):
    os.makedirs(DISCOVERY_DIR, exist_ok=True)

    timestamp = int(time.time())
    prefix = f"{name}_{timestamp}"

    # Screenshot
    screenshot_path = os.path.join(DISCOVERY_DIR, f"{prefix}.png")
    d.screenshot(screenshot_path)
    print(f"Screenshot: {screenshot_path}")

    # UI hierarchy (XML)
    xml_path = os.path.join(DISCOVERY_DIR, f"{prefix}.xml")
    xml = d.dump_hierarchy()
    with open(xml_path, "w") as f:
        f.write(xml)
    print(f"UI XML: {xml_path}")

    # Parsed elements summary
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
    print(f"Elements: {json_path} ({len(elements)} elements)")

    # Print summary
    print(f"\nKey elements:")
    for el in elements[:30]:
        text = el["text"] or el["content_desc"] or el["resource_id"]
        if text:
            click = " [clickable]" if el["clickable"] else ""
            print(f"  - {text}{click}")
    if len(elements) > 30:
        print(f"  ... and {len(elements) - 30} more (see JSON)")


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else f"screen_{int(time.time())}"
    d = connect_device()
    print(f"Capturing '{name}'...\n")
    dump_screen(d, name)
    print("\nDone.")


if __name__ == "__main__":
    main()
