# wwz-switch-lab

> **P2P-first research branch (ChatGPT-generated work).**
> This branch contains a **prototype** for WWZ's HTTPS environment discovery
> and authorization Enqueue responses, plus a separate non-native UDP relay lab.
> Neither authentication nor gameplay is confirmed working on a Switch yet.

## Current Switch experiment (use this, NOT the passive logger)

From PowerShell, in this branch, run:


~~~powershell
git switch research/chatgpt-hydra-server-mvp
git pull
.\run-mvp.ps1
~~~

Alternatively: \`py mvp_server.py --host 0.0.0.0\` after test certificates
have been generated with \`.\gen_certs.ps1\`.

**Do not use \`py server.py\` for this test.** It is the *original passive
TLS byte logger* and never sends an HTTP response. If it is running, stop
it with Ctrl+C before starting the MVP (both listen on TCP 11702/11704).

The sample routes respond to the actual observed EnvironmentInfo GUID,
then the high-confidence \`IAuthorizationService_Enqueue\` GUID. Success
means a **new RPC appears in the console logs**, not merely a 200 reply.
Share the new GUID path, request size, and error messages. **Never paste
auth request bodies, account tokens, or TLS private keys.** The initial
Enqueue password field could contain account credentials.

For technical details see
[docs/ENQUEUE_2026-10-22.md](docs/ENQUEUE_2026-10-22.md),
[docs/P2P_FIRST.md](docs/P2P_FIRST.md), and
[docs/PROTOBUF_DESCRIPTORS.md](docs/PROTOBUF_DESCRIPTORS.md).

---

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

## Original passive logger (legacy)

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
