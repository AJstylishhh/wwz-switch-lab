# Post-Dequeue fan-out: observed October 22, 2026

Research written by **OpenAI ChatGPT (GPT-6)**, not MathiasLui.

## New experimental result

The Switch successfully proceeds past locally generated environment, Enqueue, and Dequeue/SignInResult responses. At 16:59:10 it sends several RPCs to new services, all currently returning HTTP 404. **This does not mean the WWZ online connection is established.** The menu still reports "Failed to establish connection with WWZ services".

TLS 1.2 and actual decrypted HTTP POST traffic work on both 11702 and 11704. Re-running `gen_certs.ps1` is not required by this log; regenerate only if cert/key files are missing, changed or rejected.

| Service GUID | Method GUID | Bytes | Interpretation |
| --- | --- | ---: | --- |
| `fb383fc41afb42ce8c3f91bf828ce5a6` | `c81bf7e6e43e4f39b1c7256651eb3576` | 114 | Unknown: may be stats/access/config |
| `fb383fc41afb42ce8c3f91bf828ce5a6` | `f81fca3efea5407ab0cd288a2ae2b9ca` | 0 | Unknown zero-argument call |
| `fc8ff9d3e52742f38746806b2ab946a4` | `cd6d3021266746ffac6a0113e2e89e31` | 6172 / 3512 | Strong candidate: diagnostics `WriteADFPack` |
| `772eb3c6037845daa9ab86137203ccf2` | `c5aca06ab450401d9c1b3a9c522ba3f0` | 30 | Strong candidate: `IUserHeartbeatService_RegisterVersioned` |
| `6c60c0f72c1343a385bd02b2b311f402` | `096a2aba96f44f37802915dc1164746b` | 26 | Candidate: `IDataCenterService_GetDataCentersOccupation` or `IPingService_Ping` |

## Why these hypotheses

The extracted `main.rodata` contains repeated 24-byte records (GUID string
pointer, sidecar pointer, marker `0x403`). Each method's GUID precedes a
repeated service GUID. The `fc8ff...` service appears seven times (six
method positions plus final duplicate); `IDiagnosticDataService` defines
seven methods, of which some may not be in this particular build.

The latest captured diagnostic-shaped 3512-byte request contains only
three length-delimited fields of sizes 2445, 273, 785. Their encoded sizes
are **2448 + 276 + 788 = 3512**. `IDiagnosticDataService_WriteADFPack`
takes bytes data=1, bytes entries=2, and header message=3. This matches
the wire structure precisely, but the service/method GUID assignment is
not yet independently established.

The game version `0.1.DEV.8802288/PREBUILD` is **24 bytes**. A protobuf
string field containing it occupies **26 bytes**. Adding generation and
state as small integer fields produces exactly **30 bytes**, matching
`IUserHeartbeatService_RegisterVersioned`. These byte-size matches are
not proof until field types and values are checked in local captures.

## Next evidence collection

In this research branch, ask the test operator to run:

```powershell
git pull
py rpc_batch_probe.py captures
```

This operates on the **already existing** captures and displays each
new GUID path's protobuf field numbers, wire types and sizes,
plus cautious method candidates. It prints no actual field values.
Unlike `rpc_probe.py`, which chooses only one newest request,
`rpc_batch_probe.py` groups *all* unmapped methods. Send its JSON output,
not the .bin files. All raw protobuf bodies should remain private.

Do not configure blind generic successful responses to every new method.
A heartbeat requires useful polling settings, game configuration may
require data, and presence requires stable identities and session state.

For the P2P-first MVP, prioritize heartbeat and presence after these
method mappings are verified. Diagnostics should be secondary. Then
map lobby discovery/creation, peer addresses and WWZ's actual gameplay
handshake. A standalone UDP forwarding lab is already available, but is
not WWZ-native.
