# WireGuard Private Mesh Network Setup

## Architecture

All YGB devices communicate through a private WireGuard mesh network.
No public services exposed. No cloud dependency.

```
Mesh Network: 10.0.0.0/24
WireGuard Port: 51820/UDP
```

## Per-Device Setup

### 1. Install WireGuard

**Windows:**
```powershell
winget install WireGuard.WireGuard
```

**Linux:**
```bash
sudo apt install wireguard
```

**macOS:**
```bash
brew install wireguard-tools
```

### 2. Generate Device Keys

```bash
wg genkey | tee privatekey | wg pubkey > publickey
```

### 3. Device Configuration

Each device gets a unique IP in the `10.0.0.0/24` range.

**Example: Device 1 (10.0.0.1)**
```ini
# /etc/wireguard/wg0.conf
[Interface]
PrivateKey = <device1_private_key>
Address = 10.0.0.1/24
ListenPort = 51820

# Device 2
[Peer]
PublicKey = <device2_public_key>
AllowedIPs = 10.0.0.2/32
Endpoint = <device2_public_ip>:51820

# Device 3
[Peer]
PublicKey = <device3_public_key>
AllowedIPs = 10.0.0.3/32
Endpoint = <device3_public_ip>:51820
```

### 4. Start WireGuard

```bash
# Linux
sudo wg-quick up wg0

# Windows (via GUI or)
wireguard /installtunnelservice wg0.conf
```

## Firewall Rules

### Linux (iptables)
```bash
# Allow WireGuard
sudo iptables -A INPUT -p udp --dport 51820 -j ACCEPT

# Allow mesh traffic
sudo iptables -A INPUT -s 10.0.0.0/24 -j ACCEPT

# Block all other inbound
sudo iptables -A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT
sudo iptables -A INPUT -i lo -j ACCEPT
sudo iptables -P INPUT DROP
```

### Windows (PowerShell)
```powershell
# Allow WireGuard port
New-NetFirewallRule -DisplayName "WireGuard" -Direction Inbound -Protocol UDP -LocalPort 51820 -Action Allow

# Allow mesh traffic
New-NetFirewallRule -DisplayName "YGB Mesh" -Direction Inbound -RemoteAddress 10.0.0.0/24 -Action Allow
```

## Device IP Assignment

| Device | Mesh IP | Role |
|--------|---------|------|
| Primary (RTX 3050) | 10.0.0.1 | Training node |
| Laptop 2 (RTX 2050) | 10.0.0.2 | Training node |
| Laptop 3 (RTX 2050) | 10.0.0.3 | Training node |
| Mac M1 | 10.0.0.4 | Inference node |
| HDD NAS | 10.0.0.10 | Storage only |

## Security Rules

1. **No public services exposed** — only WireGuard port (51820/UDP) is open
2. **All YGB traffic** goes through the mesh (10.0.0.0/24)
3. **Device certificates** are required for all API access
4. **Private keys** never leave the device
5. **Peer list** is explicitly configured — no auto-discovery
