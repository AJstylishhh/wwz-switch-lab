# 2026-10-23: presence calls after nine heartbeat versions

Authored by **OpenAI ChatGPT (GPT-6)**. No private packet captures or Switch binaries are included.

## Supplied nine-entry remote test

The Linux server at 21:04:19 local successfully started on TCP 11701, 11702 and 11704. The Switch connected and sent EnvironmentDiscovery at 21:04:59, Enqueue/Dequeue and normal post-login traffic.

At 21:05:03.318, Heartbeat.Register returned `version_count=9`. Heartbeat.Update was observed repeatedly through 21:05:25.682 in the supplied log, with no Heartbeat.UnRegister or repeated environment discovery visible before the log ends. By comparison, the earlier four-version test unregistered in under two seconds. The first WriteADFPack diagnostics upload (21:05:03.961) had no recognized marker strings; there was no second diagnostic pack in the provided excerpt.

### Previously unmapped PresenceService requests observed

Service ID for all: `b89429154e224660837a4a307391b0b4`.

| Method ID | Seen request length | Observation |
|---|---:|---|
| `44106e2a072d4667999b814b3207e195` | 4 bytes | New after nine versions, recurring |
| `feda55b07bcf4b94b2e065a7f380d5be` | 2 bytes | New, recurring |
| `2896c4aa256e4e7290454ef6df3f1ce9` | 2 bytes | New, recurring |
| `b96449cd66864ace861786c011fdaf48` | 0 bytes | New, recurring |
| `2299e0e7d40548838e89bba0268ed3b2` | 0 bytes | Also seen in prior short-session teardown logs |

The four newly observed method GUID strings exist in the user-provided decompressed Switch NSO's GUID record table, grouped under the observed Presence service by the existing `rpc_pairs.py` structural heuristic. The exact method names and typed reply descriptors for these GUIDs are **not** established by this grouping. No method-name claim is made.

## Controlled HTTP status experiment

`enable_presence_menu_probe.py` adds **only those five exact routes** to an existing JSON config. Every route is `{"response_hex": "0800"}` (a bare ServiceResult retCode=0). This tests whether 404 responses are preventing online initialization. It is **not** a genuine presence implementation; one or more client methods may require a typed response. All other routes, endpoint IP addresses, TLS settings, and nine heartbeat values remain unchanged.

The baseline default code is unaffected until this helper is used on a route file. The helper rejects overwriting an existing nonmatching route. It is idempotent.

### Remote Linux testing

First stop the previous Python server with Ctrl+C, then:

```bash
cd /data/repos/wwz-switch-lab
git pull --ff-only
python3 -m unittest discover -s tests -p test_presence_menu_probe.py -v

# Keep a private local backup of your existing public-IP routes.
cp -p routes.remote.local.json routes.remote.prepresence.local.json
echo '/routes.remote.prepresence.local.json' >> .git/info/exclude

python3 enable_presence_menu_probe.py routes.remote.local.json

python3 mvp_server.py --host 0.0.0.0 \
  --ports 11701,11702,11704 \
  --routes routes.remote.local.json \
  --cert certs/server.crt \
  --key certs/server.key
```

Ask the Switch tester to attempt Online once and report what the Switch actually displayed. Log the new calls, the count/duration of heartbeat updates, error diagnostics and whether any 404s remain.

To restore the old local config without a new Git checkout:

```bash
cp -p routes.remote.prepresence.local.json routes.remote.local.json
```

### Windows Git checkout (local test only)

```powershell
cd "$HOME\OneDrive\Desktop\wwz-switch-lab-research"
git pull --ff-only
py -m unittest discover -s tests -p test_presence_menu_probe.py -v
Copy-Item routes.heartbeat-versions9.example.json routes.presence-test.local.json
py enable_presence_menu_probe.py routes.presence-test.local.json
py mvp_server.py --host 0.0.0.0 --ports 11701,11702,11704 --routes routes.presence-test.local.json --cert ..\wwz-switch-lab\certs\server.crt --key ..\wwz-switch-lab\certs\server.key
```

### Windows ZIP (local test only)

Download latest research ZIP at
`https://github.com/AJstylishhh/wwz-switch-lab/archive/refs/heads/research/chatgpt-hydra-server-mvp.zip`, extract beside existing certs, then:

```powershell
cd "$HOME\OneDrive\Desktop\wwz-switch-lab"
Copy-Item routes.heartbeat-versions9.example.json routes.presence-test.local.json
py enable_presence_menu_probe.py routes.presence-test.local.json
py mvp_server.py --host 0.0.0.0 --ports 11701,11702,11704 --routes routes.presence-test.local.json --cert .\certs\server.crt --key .\certs\server.key
```

Don't infer multiplayer from a healthy heartbeat alone; confirm online-menu behavior on the Switch separately. If bare Success remains insufficient, capture the *schema of response parsing* for these GUIDs rather than globally disabling 404 behavior.
