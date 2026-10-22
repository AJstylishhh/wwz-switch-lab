# Main-menu offline failure after post-login RPC fan-out (2026-10-22)

Research by OpenAI ChatGPT (GPT-6), not MathiasLui. This is a hypothesis-driven diagnostic note, not a working private server.

## Observed sequence

The collaborator reports `Failed to establish connection with WWZ services` despite seven experimental post-login RPC replies returning HTTP 200. On the test at about 19:31:02 local, the Switch made a series of post-login requests (RefreshTokens, Heartbeat.RegisterVersioned, DataCenterOccupation, WriteADFPack, PresenceConnect, Heartbeat.UpdateVersioned). Then:

- `Heartbeat.UnRegister` at 19:31:02.545
- Empty POST `fb383fc41afb42ce8c3f91bf828ce5a6.svc/f81fca3efea5407ab0cd288a2ae2b9ca` at 19:31:02.623
- Empty POST `b89429154e224660837a4a307391b0b4.svc/2299e0e7d40548838e89bba0268ed3b2` at 19:31:02.623
- Fresh environment discovery at 19:31:07.949

The two empty RPCs may be **IAccessManagementService.SignOut** and **IPresenceService.PresenceDisconnect**, respectively. The two service interfaces contain both those parameterless methods, but the exact GUID mappings have NOT been proven. This looks like client-led cleanup after failure rather than a missing required startup step. We should not return generic success to all unknown RPCs as a substitute for understanding why the session closes.

A successful HTTP 200 proves only that the client received a response; it does NOT prove its response handler accepted the semantic content. The fields currently filled in with fabricated local values (heartbeat versions, polling policy, data centers, user identity, provider optional info) need investigation and controlled testing.

## Distinct local workspace problem

The supplied PowerShell transcript reports `fatal: not a git repository` for both `git switch` and `git pull`, **even though the Python scripts run**. It also runs local tests named `test_catch_all`, `test_risk_fixes`, and `test_rpc_probe_all`, none of which are committed to this research branch. This suggests a non-Git or independently modified copy of the scripts. Preserve its entire folder, tests, captures and certificates. Do **not** run `git init`, delete it, or copy the whole folder over a fresh clone.

Suggested clean side-by-side clone, from the parent folder:

```powershell
git clone --branch research/chatgpt-hydra-server-mvp https://github.com/AJstylishhh/wwz-switch-lab.git wwz-switch-lab-research
```

The existing `captures` can be copied into the new clone for offline diagnosis. Keep certificate private keys local and do not publish them.

## Next low-risk local diagnostic

From the new research clone, after copying just the private `captures/` folder:

```powershell
py diagnostic_signal_probe.py captures
```

This scans captured `IDiagnosticDataService_WriteADFPack` requests for a strict allowlist of common error-code identifiers and prints only hit names, body-size summaries and compression hints. It does not display arbitrary strings or raw credentials. It is deliberately *not* a full decoder; if data is binary, encrypted or compressed, lack of hits proves nothing.

The main-menu connection failure could stem from incorrect **contents** inside our protobuf responses, from a missing endpoint in a separate service, or from platform/online checks not represented by Hydra `.svc` calls. We need the original client's error and state-change decision to identify the cause. Avoid implementing the P2P lobby protocol until this basic state transition succeeds.
