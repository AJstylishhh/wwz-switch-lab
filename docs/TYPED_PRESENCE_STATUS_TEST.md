# Oct 23 2026: typed presence-status response test

Author: **OpenAI ChatGPT (GPT-6)**. Experimental WWZ Switch backend; no known functional online menu or multiplayer yet.

## Observed result with five bare success stubs

From the October 23 21:18:02–21:18:58 remote Linux log, the test correctly enabled all five prior observed `ServiceResult.Success` routes (HTTP 200, `08 00`) while retaining nine heartbeat versions. Sign-in succeeded, then the client made **31 Heartbeat.Update requests**, plus 66 requests each to the three polled presence GUIDs (198 total) after sign-in. No unexpected/unknown RPCs, Heartbeat.UnRegister, or second diagnostic mismatch were present in the supplied log. The server was manually interrupted (`^C`) at the end, about 51 seconds after heartbeat registration.

This **does not prove** 200s were responsible for the stable session, since the previous nine-version baseline was also still alive at the end of its shorter (~23s) capture. We also have no game-screen observation from this run.

## Next test hypothesis: typed status, not just HTTP status

The original binary protobuf descriptor contains:

- `IPresenceService_GetStatusUser` (empty request)
- `IPresenceService_GetStatusMatchmake` (single int32 sequence ID)
- `IPresenceService_GetStatusSquad` (two int32 sequence IDs)
- `ServiceResult.ServiceResult_PresenceStatusResponse` typed extension field **334914069**
- `PresenceStatusResponse.User`=1, `Squad`=2, `Matchmake`=3
- `MatchmakeStatus.State = MatchmakeSessionState_msMenu` = 0

Observed polled request sizes map *plausibly*, but **are not independently linked to method names**:

| Method GUID (within presence service `b89429154e224660837a4a307391b0b4`) | Size | Candidate meaning |
|---|---:|---|
| `44106e2a072d4667999b814b3207e195` | 4 bytes | GetStatusSquad |
| `2896c4aa256e4e7290454ef6df3f1ce9` | 2 bytes | GetStatusMatchmake |
| `b96449cd66864ace861786c011fdaf48` | 0 bytes | GetStatusUser |

`enable_presence_status_probe.py` changes **only** these three stub responses to descriptor-shaped typed responses: empty/no-membership squad status, empty user status, and matchmaking status explicitly set to `msMenu`. All response values are hypotheses. It requires the five-route experiment already applied, refuses custom-route collisions and has `--undo` to restore the three bare `0800` replies. The two other presence methods remain bare success. Nine heartbeat entries remain unchanged.

### Linux host test

Stop the server with Ctrl+C, then:

```bash
cd /data/repos/wwz-switch-lab
git pull --ff-only
python3 -m unittest discover -s tests -p test_presence_status_probe.py -v

# Retain the previous five-success-response config for clean A/B.
cp -p routes.remote.local.json routes.remote.pretyped.local.json
echo '/routes.remote.pretyped.local.json' >> .git/info/exclude
python3 enable_presence_status_probe.py routes.remote.local.json

python3 mvp_server.py --host 0.0.0.0 \
  --ports 11701,11702,11704 \
  --routes routes.remote.local.json \
  --cert certs/server.crt \
  --key certs/server.key
```

Run Online on the Switch, capture console output and report **actual on-screen status**: is it in the online menu, still connecting, or displaying an error? Keep the server running long enough to tell whether the client advances or stays in the same three-call loop.

**Undo only this experiment** (stop Python first):

```bash
python3 enable_presence_status_probe.py routes.remote.local.json --undo
```

Or restore the exact pre-typed five-route file:

```bash
cp -p routes.remote.pretyped.local.json routes.remote.local.json
```

### Windows Git checkout

```powershell
cd "$HOME\OneDrive\Desktop\wwz-switch-lab-research"
git pull --ff-only
py -m unittest discover -s tests -p test_presence_status_probe.py -v
Copy-Item routes.heartbeat-versions9.example.json routes.presence-typed.local.json
py enable_presence_menu_probe.py routes.presence-typed.local.json
py enable_presence_status_probe.py routes.presence-typed.local.json
py mvp_server.py --host 0.0.0.0 --ports 11701,11702,11704 --routes routes.presence-typed.local.json --cert ..\wwz-switch-lab\certs\server.crt --key ..\wwz-switch-lab\certs\server.key
```

### Windows ZIP checkout

Fetch [research branch ZIP](https://github.com/AJstylishhh/wwz-switch-lab/archive/refs/heads/research/chatgpt-hydra-server-mvp.zip). From its extracted root with `certs/` transferred separately:

```powershell
cd "$HOME\OneDrive\Desktop\wwz-switch-lab"
Copy-Item routes.heartbeat-versions9.example.json routes.presence-typed.local.json
py enable_presence_menu_probe.py routes.presence-typed.local.json
py enable_presence_status_probe.py routes.presence-typed.local.json
py mvp_server.py --host 0.0.0.0 --ports 11701,11702,11704 --routes routes.presence-typed.local.json --cert .\certs\server.crt --key .\certs\server.key
```

**Interpretation:** This only tests typed status payloads. Even if the game accepts them and shows Online, parties and matchmaking still need real session state, identities, and multiplayer transport. If there is no behavioral change, identify actual native method→GUID bindings and client response parsing before altering more values.
