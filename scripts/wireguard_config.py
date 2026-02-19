"""
wireguard_config.py — WireGuard Mesh Config Generator
=====================================================

Generates wg0.conf files for each device in the mesh.
IP range: 10.0.0.0/24 (max 254 devices).
Reads device list from config/devices.json.
Outputs configs to config/wireguard/<device_id>.conf.

MANUAL STEPS REQUIRED:
  1. Install WireGuard on each device
  2. Copy generated config to /etc/wireguard/wg0.conf
  3. Enable: wg-quick up wg0
  4. Configure firewall to block all public inbound except WireGuard port
"""

import os
import json
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEVICES_PATH = os.path.join(PROJECT_ROOT, "config", "devices.json")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "config", "wireguard")
MESH_SUBNET = "10.0.0"
LISTEN_PORT = 51820


def load_devices() -> list:
    """Load device registry."""
    if not os.path.exists(DEVICES_PATH):
        print(f"ERROR: {DEVICES_PATH} not found. Run pairing first.")
        return []
    with open(DEVICES_PATH) as f:
        return json.load(f).get("devices", [])


def generate_configs(devices: list):
    """Generate WireGuard config for each device."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    if not devices:
        print("No devices registered. Nothing to generate.")
        return

    for i, device in enumerate(devices):
        device_id = device.get("device_id", f"device_{i}")
        ip = f"{MESH_SUBNET}.{i + 1}"

        # Generate config
        conf_lines = [
            "[Interface]",
            f"# Device: {device_id}",
            f"Address = {ip}/24",
            f"ListenPort = {LISTEN_PORT}",
            f"# PrivateKey = <PASTE DEVICE PRIVATE KEY HERE>",
            "",
        ]

        # Add peers (all other devices)
        for j, peer in enumerate(devices):
            if j == i:
                continue
            peer_id = peer.get("device_id", f"device_{j}")
            peer_ip = f"{MESH_SUBNET}.{j + 1}"
            conf_lines.extend([
                f"[Peer]",
                f"# {peer_id}",
                f"# PublicKey = <PASTE {peer_id} PUBLIC KEY HERE>",
                f"AllowedIPs = {peer_ip}/32",
                f"PersistentKeepalive = 25",
                "",
            ])

        # Write config
        conf_path = os.path.join(OUTPUT_DIR, f"{device_id}.conf")
        with open(conf_path, "w") as f:
            f.write("\n".join(conf_lines))
        print(f"  Generated: {conf_path}")

    # Write firewall rules template
    fw_path = os.path.join(OUTPUT_DIR, "firewall_rules.sh")
    with open(fw_path, "w") as f:
        f.write("#!/bin/bash\n")
        f.write("# Firewall rules for WireGuard mesh\n")
        f.write("# Run on each device after WireGuard is configured\n\n")
        f.write(f"# Allow WireGuard\n")
        f.write(f"sudo ufw allow {LISTEN_PORT}/udp\n\n")
        f.write(f"# Allow mesh traffic\n")
        f.write(f"sudo ufw allow from {MESH_SUBNET}.0/24\n\n")
        f.write(f"# Block all other inbound\n")
        f.write(f"sudo ufw default deny incoming\n")
        f.write(f"sudo ufw default allow outgoing\n")
        f.write(f"sudo ufw enable\n")
    print(f"  Generated: {fw_path}")


def main():
    print("=== WireGuard Mesh Config Generator ===")
    devices = load_devices()
    print(f"  Devices registered: {len(devices)}")
    generate_configs(devices)
    print("\nDone. Manual steps:")
    print("  1. Install WireGuard: sudo apt install wireguard")
    print("  2. Generate keys: wg genkey | tee privatekey | wg pubkey > publickey")
    print("  3. Edit config with real keys")
    print("  4. Copy to /etc/wireguard/wg0.conf")
    print("  5. Enable: sudo wg-quick up wg0")


if __name__ == "__main__":
    main()
