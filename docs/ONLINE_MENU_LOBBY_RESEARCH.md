# 2026-10-23: WWZ Switch online menu reached; lobby creation still fails

Author: **OpenAI ChatGPT (GPT-6)**. All code on `research/chatgpt-hydra-server-mvp`, never `main`.

## Hardware-confirmed milestone

The Switch tester reported **the main menu displays online** with nine `UserVersions` entries and the opt-in typed PresenceStatusResponse test. The tester also reported **creating a lobby returns to the selection screen**, so no lobby success or multiplayer has been verified.

The provided server log at 21:38:48–21:41:08 local confirms:
- EnvironmentDiscovery on TCP 11702 and experimental Enqueue/Dequeue on TCP 11704 completed;
- Heartbeat.Register and repeated Heartbeat.Update with **nine** version values continued throughout;
- a RedLynx HTTP/TLS connection reached **TCP 11701**, which had previously not been observed, and requested `/redlynx.api.endpointdispatcher.endpointdispatcherapi/getenvironmentinfo` (147 bytes);
- some new PresenceService GUIDs received HTTP 404 because handlers were not implemented;
- the game-close stack traces contain `BrokenPipeError` and `ConnectionResetError` while Python's HTTP handler waits for another request; they do not imply auth failure.

### Six newly observed unknown PresenceService methods

All are on `b89429154e224660837a4a307391b0b4.svc`.

| Method GUID | Request length(s) | Count in submitted log |
|---|---|---:|
| `b2a1ab68eb464d7796c4e9f49247d3c8` | 107 and 164 bytes | 183 |
| `67cdaf75ca604bd993ad9f1db0c3f812` | 167 or 218 bytes | 4 |
| `f9dcd75c457145e7a8b4d5e619171fc1` | 0 bytes | 4 |
| `5df1122df8884a408c2b804153dc90f1` | 6 bytes | 1 |
| `44a718e4c7514684b5259e0879e98c63` | 114 bytes | 1 |
| `dfd72da619924665a51e16f74e813f13` | 2 bytes | 1 |

Request lengths and timing are observed facts. **Do not claim GUID-to-method meanings based on length alone**; the extracted client descriptor contains candidates like `SquadSetSettings`, `SquadSetGameData`, `SquadLeave`, `SetProperty`, `MatchmakeStart`, etc., but this log alone does not prove mappings.

The 183-request method may involve repeated status/property synchronization. Its 107/164-byte transition and the rare setup calls provide promising leverage to identify the lobby-create blocker. The single `RedLynx getenvironmentinfo` method must also be mapped before returning a fabricated response.

## Instrumentation patch for next Switch attempt

`request_shape.py` and `mvp_server.py` now record **only** top-level protobuf field numbers, wire types, and encoded byte lengths for *unknown* PresenceService GUIDs and the observed RedLynx method. They never print values, text, join codes, account tokens, addresses, or packet bytes. Packet inspection is bounded to 2048 bytes/24 top-level fields. Everything else (typed presence, nine version values, public IP route, port config) remains unchanged.

The HTTP handler now catches only normal `BrokenPipeError`, `ConnectionResetError`, `ConnectionAbortedError`, and TLS unexpected peer-close errors. It intentionally **does not** conceal actual malformed-request exceptions or server programming errors.

The patch **does not** implement successful lobby creation. Unknown calls remain HTTP 404 until their true semantics are understood.

### Linux remote host

Stop the previous Python server via Ctrl+C, then:

```bash
cd /data/repos/wwz-switch-lab
git pull --ff-only
python3 -m unittest discover -s tests -p test_lobby_request_shapes.py -v

# Keep the existing nine-version + typed-presence + public-IP configuration.
python3 mvp_server.py --host 0.0.0.0 \
  --ports 11701,11702,11704 \
  --routes routes.remote.local.json \
  --cert certs/server.crt --key certs/server.key
```

Have the tester sign in, *create a lobby once*, and report the exact on-screen result. Collect the `Unimplemented RPC request shape` and `Unimplemented RedLynx environment request shape` lines, along with the short sequence around that click. A first goal is distinguishing user property updates (one long string) from structured squad create/options requests.

### Windows PowerShell Git checkout

```powershell
cd "$HOME\OneDrive\Desktop\wwz-switch-lab-research"
git pull --ff-only
py -m unittest discover -s tests -p test_lobby_request_shapes.py -v
py mvp_server.py --host 0.0.0.0 --ports 11701,11702,11704 --routes routes.presence-typed.local.json --cert ..\wwz-switch-lab\certs\server.crt --key ..\wwz-switch-lab\certs\server.key
```

Only use `routes.presence-typed.local.json` if prepared via `enable_presence_menu_probe.py` and `enable_presence_status_probe.py` from the previous test.

### Windows ZIP

Download latest [research branch ZIP](https://github.com/AJstylishhh/wwz-switch-lab/archive/refs/heads/research/chatgpt-hydra-server-mvp.zip), extract beside existing certs:

```powershell
cd "$HOME\OneDrive\Desktop\wwz-switch-lab"
Copy-Item routes.heartbeat-versions9.example.json routes.presence-typed.local.json
py enable_presence_menu_probe.py routes.presence-typed.local.json
py enable_presence_status_probe.py routes.presence-typed.local.json
py -m unittest discover -s tests -p test_lobby_request_shapes.py -v
py mvp_server.py --host 0.0.0.0 --ports 11701,11702,11704 --routes routes.presence-typed.local.json --cert .\certs\server.crt --key .\certs\server.key
```

**Next after shape evidence:** recover exact GUID→request/response type using static client references or further controlled request captures, implement real local squad/lobby membership state, then investigate game-session signalling and UDP separately. Avoid blindly answering all methods with 0800; lobby state requires consistent identity/session data and clients may validate response type.
