# WWZ 2026-10-23: collaborator ZIP versus research, first isolated A/B

Authored by **OpenAI ChatGPT (GPT-6)** on research branch. This note is distilled from the user's privately uploaded `wwz-switch-lab - Copy.zip`. **Do not commit or share its raw `captures/`, `captures.zip`, certificates, original payloads or account data.**

## Observations supported by captures

- The October 23 **14:54:57Z** EnvironmentDiscovery was followed by Enqueue, Dequeue, RefreshTokens, HeartbeatRegister, DataCenterOccupation, diagnostics, HeartbeatUpdate and PresenceConnect.
- After PresenceConnect, a new empty-body presence service method with method GUID `55b1adc4fbe7404886e99b22752058fe` appeared. The local ZIP's later source calls this `presence_essential`. The name is provisional, not verified against an official method descriptor.
- The session then sent **265 Heartbeat.UpdateVersioned requests**, with additional RefreshTokens, until **15:00:02Z**, around **304.5 seconds** after discovery. It then made terminal presence, heartbeat-unregister and access-management calls.
- Surrounding short sessions resumed EnvironmentDiscovery after about 5 seconds.
- Diagnostic uploads from short sessions near 14:53Z, 15:01Z, 15:03Z and 15:06Z contain the specific message **`autogen VersionDataType_Last does not corresponds with backend values`**. No occurrence of that message was found in the decompressed diagnostic uploads from the five-minute session. This is a correlation; telemetry is not a complete event trace.
- ZIP contains `presence_backoff_seconds: 300` and repeated int64 UserVersions reply code. Research branch currently sends ReturnAvailableSeconds=0 and an empty UserVersions submessage. These differences are independent candidates. Current ZIP code was modified after some captures, so historical response parameters cannot be reconstructed with certainty from the latest files.

## First isolated test

`routes.presence-300.example.json` is the exact `routes.environment-production-shape.example.json` configuration **plus only** `presence_available_seconds: 300` for the PresenceConnect handler. No heartbeat response, entitlement, provider tokens, environment or UDP behavior is modified.

Test this once with the same Switch setup and observe whether Heartbeat.UnRegister remains immediate or the session stays up. The experiment is inconclusive if no new requests arrive. If it remains immediate, the next controlled candidate should be UserVersions.Versions with nonempty, stable int64 count **in both** heartbeat register and update responses, informed by the client-side mismatch evidence. Do not guess a specific count as established fact.

Command:

```powershell
cd "$HOME\OneDrive\Desktop\wwz-switch-lab-research"
git pull --ff-only
py -m unittest discover -s tests -p test_presence_duration.py -v
py mvp_server.py --host 0.0.0.0 --ports 11701,11702,11704 --routes routes.presence-300.example.json --cert ..\wwz-switch-lab\certs\server.crt --key ..\wwz-switch-lab\certs\server.key
```

Stop all prior lab listeners before running. All changes confined to `research/chatgpt-hydra-server-mvp`.
