"""Tap the giveaway button in the current stream and capture the result."""
import uiautomator2 as u2
import os
import time
import json

DISCOVERY_DIR = os.path.join(os.path.dirname(__file__), "discovery")


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
    for el in elements[:40]:
        text = el["text"] or el["content_desc"] or el["resource_id"]
        if text:
            click = " [clickable]" if el["clickable"] else ""
            print(f"  - {text}{click}")
    if len(elements) > 40:
        print(f"  ... and {len(elements) - 40} more")


d = u2.connect_usb()
print(f"Connected: {d.info.get('productName', 'Unknown')}")

# Try to find and tap the Giveaway button
giveaway = d(text="Giveaway")
if giveaway.exists:
    giveaway.click()
    print("Tapped 'Giveaway' button")
    time.sleep(2)
    capture(d, "giveaway_panel")
else:
    print("No 'Giveaway' button found on screen")
    capture(d, "no_giveaway")
