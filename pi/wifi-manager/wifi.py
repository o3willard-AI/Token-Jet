#!/usr/bin/env python3
"""Wi-Fi management CLI for the Token-Jet pi wifi-manager skill."""

import argparse
import json
import subprocess
import sys


def run(args, sudo=False, timeout=15):
    cmd = (["sudo"] if sudo else []) + ["nmcli"] + list(args)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout, r.stderr, r.returncode
    except subprocess.TimeoutExpired:
        return "", "Command timed out", -1
    except FileNotFoundError:
        return "", "nmcli not found", -1


def get_wifi_device():
    out, _, _ = run(["-t", "-f", "DEVICE,TYPE", "device"])
    for line in out.splitlines():
        parts = line.split(":", 1)
        if len(parts) == 2 and parts[1].strip() == "wifi":
            return parts[0].strip()
    return None


def get_saved_ssids():
    out, _, _ = run(["-t", "-f", "NAME,TYPE", "connection", "show"])
    saved = set()
    for line in out.splitlines():
        parts = line.split(":", 1)
        if len(parts) == 2 and "wireless" in parts[1].lower():
            saved.add(parts[0].strip())
    return saved


def signal_to_bars(signal):
    """Convert 0-100 signal to 4-block bar string."""
    filled = min(4, signal // 25)
    chars = ["▂", "▄", "▆", "█"]
    return "".join(chars[:filled]) + "_" * (4 - filled)


def parse_wifi_list(output):
    """Parse nmcli -m multiline device wifi list into a list of dicts.

    nmcli multiline output has no blank lines between entries — the repeating
    IN-USE field marks the start of each new entry, not a blank line.
    """
    networks = []
    current = {}

    for line in output.splitlines():
        if not line.strip():
            continue

        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()

        if key == "IN-USE":
            # New entry starting — save the previous one if it had an SSID
            if "ssid" in current:
                networks.append(current)
            current = {"in_use": val == "*"}
        elif key == "SSID":
            current["ssid"] = val
        elif key == "SIGNAL":
            try:
                current["signal"] = int(val)
            except ValueError:
                current["signal"] = 0
        elif key == "BARS":
            current["bars"] = val
        elif key == "SECURITY":
            current["security"] = val if val not in ("--", "") else ""

    if "ssid" in current:
        networks.append(current)

    return networks


def cmd_status():
    dev = get_wifi_device()
    if not dev:
        print(json.dumps({"error": "No Wi-Fi device found"}))
        return 1

    out, _, _ = run(["-t", "-f", "WIFI", "radio"])
    radio_enabled = out.strip().lower() == "enabled"

    if not radio_enabled:
        print(json.dumps({"enabled": False, "device": dev}))
        return 0

    out, _, _ = run(["-t", "-f", "DEVICE,STATE,CONNECTION", "device", "status"])
    state = "disconnected"
    connected_to = None
    for line in out.splitlines():
        parts = line.split(":", 2)
        if len(parts) >= 2 and parts[0] == dev:
            state = parts[1]
            connected_to = parts[2] if len(parts) > 2 and parts[2] else None
            break

    ip = None
    out2, _, _ = run(["-t", "-f", "IP4.ADDRESS", "device", "show", dev])
    for line in out2.splitlines():
        if line.startswith("IP4.ADDRESS"):
            ip = line.split(":", 1)[1].strip() or None
            break

    print(json.dumps({
        "enabled": True,
        "device": dev,
        "state": state,
        "connected_to": connected_to,
        "ip": ip,
    }))
    return 0


def cmd_scan():
    dev = get_wifi_device()
    if not dev:
        print(json.dumps({"error": "No Wi-Fi device found"}))
        return 1

    out, _, _ = run(["-t", "-f", "WIFI", "radio"])
    if out.strip().lower() != "enabled":
        print(json.dumps({"error": "Wi-Fi is disabled. Use 'wifi on' first."}))
        return 1

    # Trigger rescan (ignore errors — device may already be scanning)
    run(["device", "wifi", "rescan"], sudo=True, timeout=10)

    out, err, rc = run(
        ["-m", "multiline", "-f", "IN-USE,BSSID,SSID,SIGNAL,BARS,SECURITY",
         "device", "wifi", "list"]
    )
    if rc != 0:
        print(json.dumps({"error": err.strip() or "Scan failed"}))
        return 1

    networks = parse_wifi_list(out)
    saved = get_saved_ssids()

    seen = set()
    result = []
    for n in networks:
        ssid = n.get("ssid", "")
        if not ssid or ssid == "--" or ssid in seen:
            continue
        seen.add(ssid)
        signal = n.get("signal", 0)
        bars = n.get("bars") or signal_to_bars(signal)
        result.append({
            "ssid": ssid,
            "signal": signal,
            "bars": bars,
            "security": n.get("security", ""),
            "connected": n.get("in_use", False),
            "saved": ssid in saved,
        })

    result.sort(key=lambda x: -x["signal"])
    print(json.dumps({"networks": result}))
    return 0


def cmd_on():
    _, err, rc = run(["radio", "wifi", "on"], sudo=True)
    if rc != 0:
        print(json.dumps({"success": False, "error": err.strip()}))
        return 1
    print(json.dumps({"success": True}))
    return 0


def cmd_off():
    _, err, rc = run(["radio", "wifi", "off"], sudo=True)
    if rc != 0:
        print(json.dumps({"success": False, "error": err.strip()}))
        return 1
    print(json.dumps({"success": True}))
    return 0


def cmd_connect(ssid, password=None):
    dev = get_wifi_device()
    if not dev:
        print(json.dumps({"error": "No Wi-Fi device found"}))
        return 1

    args = ["device", "wifi", "connect", ssid]
    if password:
        args += ["password", password]
    if dev:
        args += ["ifname", dev]

    out, err, rc = run(args, sudo=True, timeout=30)
    combined = (out + err).strip()

    if rc != 0:
        print(json.dumps({"success": False, "error": combined}))
        return 1

    print(json.dumps({"success": True, "message": combined}))
    return 0


def cmd_disconnect():
    dev = get_wifi_device()
    if not dev:
        print(json.dumps({"error": "No Wi-Fi device found"}))
        return 1

    out, err, rc = run(["device", "disconnect", dev], sudo=True)
    if rc != 0:
        print(json.dumps({"success": False, "error": (out + err).strip()}))
        return 1
    print(json.dumps({"success": True}))
    return 0


def cmd_forget(ssid):
    # Find all wireless connection profiles matching this SSID name
    out, _, _ = run(["-t", "-f", "NAME,TYPE", "connection", "show"])
    matched = []
    for line in out.splitlines():
        parts = line.split(":", 1)
        if len(parts) == 2 and "wireless" in parts[1].lower() and parts[0].strip() == ssid:
            matched.append(parts[0].strip())

    if not matched:
        print(json.dumps({"success": False, "error": f"No saved profile found for '{ssid}'"}))
        return 1

    errors = []
    for name in matched:
        _, err, rc = run(["connection", "delete", name], sudo=True)
        if rc != 0:
            errors.append(err.strip())

    if errors:
        print(json.dumps({"success": False, "error": "; ".join(errors)}))
        return 1

    print(json.dumps({"success": True}))
    return 0


def cmd_forget_all():
    """Delete every saved Wi-Fi connection profile — used by /secure-jet."""
    out, _, _ = run(["-t", "-f", "NAME,TYPE", "connection", "show"])
    to_delete = []
    for line in out.splitlines():
        parts = line.split(":", 1)
        if len(parts) == 2 and "wireless" in parts[1].lower():
            name = parts[0].strip()
            if name:
                to_delete.append(name)

    if not to_delete:
        print(json.dumps({"success": True, "deleted": [], "count": 0}))
        return 0

    deleted = []
    errors = []
    for name in to_delete:
        _, err, rc = run(["connection", "delete", name], sudo=True)
        if rc == 0:
            deleted.append(name)
        else:
            errors.append(err.strip() or f"failed to delete '{name}'")

    if errors:
        print(json.dumps({"success": False, "deleted": deleted, "errors": errors}))
        return 1

    print(json.dumps({"success": True, "deleted": deleted, "count": len(deleted)}))
    return 0


def main():
    p = argparse.ArgumentParser(
        description="Wi-Fi management for Token-Jet",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = p.add_subparsers(dest="command")

    sub.add_parser("status",     help="Show radio state and current connection")
    sub.add_parser("scan",       help="Scan and list nearby networks as JSON")
    sub.add_parser("on",         help="Enable Wi-Fi radio")
    sub.add_parser("off",        help="Disable Wi-Fi radio")
    sub.add_parser("disconnect", help="Disconnect from current network")
    sub.add_parser("forget-all", help="Delete ALL saved Wi-Fi profiles (used by /secure-jet)")

    c = sub.add_parser("connect", help="Connect to a network")
    c.add_argument("ssid", help="Network name (SSID)")
    c.add_argument("--password", "-p", help="WPA/WPA2/WPA3 passphrase")

    f = sub.add_parser("forget", help="Delete a saved connection profile")
    f.add_argument("ssid", help="Network name to forget")

    args = p.parse_args()

    dispatch = {
        "status":     cmd_status,
        "scan":       cmd_scan,
        "on":         cmd_on,
        "off":        cmd_off,
        "disconnect": cmd_disconnect,
        "forget-all": cmd_forget_all,
        "connect":    lambda: cmd_connect(args.ssid, getattr(args, "password", None)),
        "forget":     lambda: cmd_forget(args.ssid),
    }

    fn = dispatch.get(args.command)
    if fn is None:
        p.print_help()
        sys.exit(1)

    sys.exit(fn())


if __name__ == "__main__":
    main()
