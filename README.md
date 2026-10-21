# wwz-switch-lab

**Lab only** — TLS terminator + traffic logger for World War Z Switch online API.

Not a playable private server.

## Your network

| Device | IP |
|--------|-----|
| PC (ICS) | **192.168.137.1** |
| Switch | 192.168.137.x |

## What we learned from your capture

- Switch connects to **TCP 11702** with **TLS**
- SNI = **`wwz.wwzapi.com`**
- ALPN = `http/1.1` and `h2`

This build **completes the TLS handshake** with a lab certificate and logs **decrypted** bytes (and HTTP headers if the client sends them).

If the Switch **pins** Saber’s real certificate, handshake will fail — that result is still useful.

---

## Setup (once)

```powershell
cd "C:\Users\Asif Ali IBS\OneDrive\Desktop\wwz-switch-lab"
git pull

# Create certs for wwz.wwzapi.com
.\gen_certs.ps1
```

If OpenSSL is installed (you used it for Dying Light), `gen_certs.ps1` writes both `certs\server.crt` and `certs\server.key`.

Allow Python through the firewall (or turn Private firewall off only while testing).

### Switch hosts

```text
192.168.137.1  wwz.wwzapi.com
192.168.137.1  wwz-production.wwzapi.com
192.168.137.1  wwzprod.wwzapi.com
192.168.137.1  rlx.hydrapi.net
192.168.137.1  rlxp1a1l.hydrapi.net
```

---

## Run

```powershell
cd "C:\Users\Asif Ali IBS\OneDrive\Desktop\wwz-switch-lab"
py server.py
```

Expected:

```text
[WWZ Lab] TLS listening 0.0.0.0:11702
[WWZ Lab] TLS listening 0.0.0.0:11704
```

Then open WWZ online on the Switch.

### Good signs

- `TLS OK peer=192.168.137.x`
- Decrypted data / `--- HTTP head ---`

### If you see `TLS handshake FAILED`

Likely **certificate pinning**. Paste the error line; lab still documented the protocol as TLS+HTTPS-style API.

---

## Files

| File | Role |
|------|------|
| `server.py` | TLS listen + decrypt log |
| `gen_certs.ps1` | Lab cert for `wwz.wwzapi.com` |
| `hosts-snippet.txt` | Atmosphere hosts |
| `logs/` | Saved sessions |
