# wwz-switch-lab

**Lab only** — not a playable World War Z private server.

Redirects the CFW Switch to your PC and logs bytes on **TCP 11702 / 11704**.

## Fixed lab network (your setup)

| Device | IP |
|--------|-----|
| **PC (ICS gateway)** | **`192.168.137.1`** |
| Switch | `192.168.137.x` (e.g. `.122`, `.141`) |

Hosts file already uses **`192.168.137.1`** — no need to edit IPs unless your network changes.

| Host | Official (blocked by hosts) | Lab target |
|------|-----------------------------|------------|
| `wwz.wwzapi.com` | `51.124.204.22` | `192.168.137.1` |
| `wwz-production.wwzapi.com` | same | `192.168.137.1` |
| Ports | **11702**, **11704** | same on PC |

Stack: **Saber/Redlynx Hydra** (not NEX).

---

## Step 1 — PC: run the lab server

```powershell
cd $env:USERPROFILE\Desktop
git clone https://github.com/AJstylishhh/wwz-switch-lab.git
cd wwz-switch-lab

# Admin PowerShell once — firewall
New-NetFirewallRule -DisplayName "WWZ Lab 11702" -Direction Inbound -Protocol TCP -LocalPort 11702 -Action Allow
New-NetFirewallRule -DisplayName "WWZ Lab 11704" -Direction Inbound -Protocol TCP -LocalPort 11704 -Action Allow

python server.py
```

Or: `.\run.ps1`

Expected:

```text
[WWZ Lab] listening TCP 0.0.0.0:11702
[WWZ Lab] listening TCP 0.0.0.0:11704
[WWZ Lab] waiting for Switch…
```

Need Python 3 + **Add to PATH**. Logs go to `logs/`.

Keep **ICS / the 192.168.137.x link** up so the Switch can reach `192.168.137.1`.

---

## Step 2 — Switch: hosts (copy-paste)

Edit `atmosphere/hosts/emummc.txt` **or** `sysmmc.txt`:

```text
192.168.137.1  wwz.wwzapi.com
192.168.137.1  wwz-production.wwzapi.com
192.168.137.1  wwzprod.wwzapi.com
192.168.137.1  rlx.hydrapi.net
192.168.137.1  rlxp1a1l.hydrapi.net
```

Same content is in `hosts-snippet.txt`.

`atmosphere/config/system_settings.ini`:

```text
[atmosphere]
enable_dns_mitm = u8!0x1
```

**Full power off**, then on.

---

## Step 3 — Test

1. `python server.py` running on PC  
2. WWZ → **online** co-op / matchmaking  
3. PC should show `CONNECT from 192.168.137.x` + hex  

Paste those lines (or a `logs/*.log` file).

| Log clue | Next step |
|----------|-----------|
| Starts with `16 03` | Likely TLS |
| Other binary | Custom framing |
| No CONNECT | ICS down, wrong hosts file (emu vs sys), or firewall |

---

## Scope

Accept + log only. Not matchmaking or missions. CFW DNS mitm keeps traffic on your LAN lab, not official servers.
