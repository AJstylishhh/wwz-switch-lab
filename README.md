# wwz-switch-lab

**Lab only** — not a playable World War Z private server.

Goal: redirect the Switch away from official `wwzapi.com` and see what the CFW client sends to **TCP 11702 / 11704**.

Captured endpoints (from your pcaps):

| Host | IP (example) | Ports |
|------|----------------|-------|
| `wwz.wwzapi.com` | `51.124.204.22` | **11702**, **11704** |
| `wwz-production.wwzapi.com` | same | same |
| `rlx.hydrapi.net` | (CNAME) | TBD |

Stack is **Saber/Redlynx Hydra**, not Nintendo NEX.

---

## You need

- Windows PC (same LAN / ICS as Switch)
- Python 3.10+ ([python.org](https://www.python.org/downloads/) — tick **Add to PATH**)
- Atmosphere CFW Switch (DNS mitm hosts)

---

## Step 1 — PC: get your LAN IP

PowerShell:

```powershell
Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike "127.*" } | Select-Object IPAddress, InterfaceAlias
```

Use the IP the Switch can reach (e.g. `192.168.137.1` on ICS, or `192.168.1.x` on Wi‑Fi).

---

## Step 2 — PC: open firewall + run the lab server

```powershell
cd $env:USERPROFILE\Desktop
git clone https://github.com/AJstylishhh/wwz-switch-lab.git
cd wwz-switch-lab

# Allow ports (run PowerShell as Administrator once)
New-NetFirewallRule -DisplayName "WWZ Lab 11702" -Direction Inbound -Protocol TCP -LocalPort 11702 -Action Allow
New-NetFirewallRule -DisplayName "WWZ Lab 11704" -Direction Inbound -Protocol TCP -LocalPort 11704 -Action Allow

python server.py
```

You should see:

```text
[WWZ Lab] listening TCP 0.0.0.0:11702
[WWZ Lab] listening TCP 0.0.0.0:11704
[WWZ Lab] waiting for Switch…
```

Leave this window open.

Optional: `python server.py --host 0.0.0.0 --ports 11702,11704`

Logs are written to `logs/` (hex + raw `.bin` per connection).

---

## Step 3 — Switch: Atmosphere hosts

On the SD card, edit **one** of:

- `atmosphere/hosts/emummc.txt` (emuMMC)
- `atmosphere/hosts/sysmmc.txt` (sysMMC)

Add (replace `YOUR_PC_IP`):

```text
# WWZ lab — force game API to PC
YOUR_PC_IP  wwz.wwzapi.com
YOUR_PC_IP  wwz-production.wwzapi.com
YOUR_PC_IP  wwzprod.wwzapi.com
YOUR_PC_IP  rlx.hydrapi.net
YOUR_PC_IP  rlxp1a1l.hydrapi.net
```

Also ensure DNS mitm is on in `atmosphere/config/system_settings.ini`:

```text
[atmosphere]
enable_dns_mitm = u8!0x1
```

Fully power off the Switch, then power on.

Copy-paste template: see `hosts-snippet.txt`.

---

## Step 4 — Test

1. PC: `python server.py` running  
2. Switch: open **World War Z** → try **online** co-op / matchmaking  
3. Watch the PC console  

### What success looks like (lab)

- Lines like `[11702] connection from 192.168.137.x`
- Hex dumps in the console and files under `logs/`

### What it does **not** do

- Full matchmaking, parties, or missions  
- Speak Hydra protocol yet — **only accept + log**  

If you see **TLS ClientHello** (`16 03 01`…) the next step is TLS/certs.  
If you see **plain binary** with no TLS, we can start mapping message formats.

Paste the first 20–30 log lines here after a test.

---

## CFW note

With hosts + DNS mitm, the Switch should hit **your PC**, not official `51.124.204.22`.  
If nothing connects: wrong hosts file (emu vs sys), wrong PC IP, firewall, or game not entering online.

---

## Legal / scope

Research lab for a client you own on CFW. No game assets or Nintendo/Saber secrets are included. Not affiliated with Saber, Redlynx, or Nintendo.
