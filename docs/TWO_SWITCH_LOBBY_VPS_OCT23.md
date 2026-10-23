# 2026-10-23: two-Switch partial VPS trace, lobby/matchmaking RPC test

Authored by **OpenAI ChatGPT (GPT-6)**. Changes on `research/chatgpt-hydra-server-mvp` ONLY.

## Hardware results and test constraints

- Friend with **Switch OLED, system FW 22.5.0, Atmosphère 1.11.2**: WWZ main menu shows online. Public/private lobby creation enters lobby briefly then returns to selection. Selecting the game's separate Multiplayer menu item opens Nintendo eShop and prompts for a system update.
- Second tester with older Switch and **system FW 22.5.0, Atmosphère 1.12.1** (after downgrade from system FW 23.0.1): same lobby failure, but selecting Multiplayer reveals `Find Match` and `Classes`. This is an observation, **not proof Atmosphère versions cause the difference**.
- Nintendo's eShop/online entitlement/update path is separate from this project's experimental Hydra server. Do not assume its UI can be fixed by replying to WWZ Presence RPCs. Focus the next Hydra test on the public/private lobby failure first.
- The provided console scrollback is **not the full session**: 1903 lines, 21:11:21–21:15:32. It begins while a session is already running, and a separate login appears at 21:12:54. Source doesn't include client identifiers, so it cannot reliably attribute later requests or the 21:14:09 UnRegister to an individual Switch. Never call the full multi-client test 'stable'.

## Counts and wire facts from the 1903-line supplied excerpt

Of **696 POST requests**:
- 450 to Presence GUID `b2a1ab68eb464d7796c4e9f49247d3c8`: **421 x 107 bytes**, **13 x 164 bytes**, **12 x 163 bytes**, **4 x 165 bytes**. Each consists of one length-delimited field 1 (size 105/161/160/162), potentially a long property/game-data string.
- 176 Heartbeat.Update requests, continuing even with 404s elsewhere; one UnRegister at 21:14:09.
- 8 RedLynx `/redlynx.api.endpointdispatcher.endpointdispatcherapi/getenvironmentinfo` requests (147 bytes) over TLS 11701; existing generic protobuf parser reports `format=unknown` rather than valid protobuf. **Don't return a guessed Hydra protobuf envelope on this separate endpoint**.
- Five calls to Presence GUID `67cdaf75ca604bd993ad9f1db0c3f812` (3 x 167 bytes, 2 x 144): the request field layout is four repeated field1 messages, field2 message, field3 string and repeated field4 messages. This is an exact **field-number/type/repetition match** for the client's `IPresenceService_MatchmakeStart` schema in `proto.proto`: field1 `dcPings`, field2 `mmOptions`, field3 `playlist`, field4 `variants`. Identifying the specific GUID remains based on this shape comparison, not native callback xrefs; this makes it **high confidence, not conclusive proof**.
- Other unknown Presence GUIDs and counts: `5df1122d...` 2 x 6 bytes (one nested message), `44a718e4...` 4 x 115 bytes (one string-like field), `dfd72da6...` 2 x 2 bytes (scalar field), `f9dcd75c...` 5 empty requests, `b2ba5509...` 4 x 2 bytes (scalar field). Candidate functions: `SquadSetSettings`, `SquadSetGameData`, `SquadSetInvitesState`, `MatchmakeStop`, `SetGameClientState`; **not validated GUID mappings**.
- No complete evidence of a two-player joined lobby or a functional multiplayer game session.

The analyzed Switch NSO `main` SHA-256 is `0e93e33bf2026f031dfcbc0bf51eba85cd6ee1e7e2305f11abecfaddded6560c`. The embedded descriptor `proto.proto` SHA-256 is `a5def4a263d211158fc652642693867fbbebc1639994b107e5dcced7b7e28534`. Source binaries and raw identity-bearing requests are not committed.

## Next test: one-at-a-time 404→Success A/B

`enable_lobby_rpc_probe.py` adds seven **exact observed** Presence RPCs returning bare protobuf `ServiceResult(retCode=0)`, hex `08 00`. No new authentication code, shared state, client identity, local lobby membership, typed matchmaking response, or RedLynx response is implemented. It deliberately does **not** claim multiplayer or a complete lobby service. This is a narrow test of whether the existing 404s are the immediate UI blocker.

### VPS (already has working nine-heartbeat + typed-presence config)

Stop the Python process with Ctrl+C:

```bash
cd /opt/wwz-switch-lab
git pull --ff-only
python3 -m unittest discover -s tests -p test_lobby_rpc_probe.py -v

cp -p routes.remote.local.json routes.remote.prelobby.local.json
echo '/routes.remote.prelobby.local.json' >> .git/info/exclude

python3 enable_lobby_rpc_probe.py routes.remote.local.json

mkdir -p logs
echo '/logs/' >> .git/info/exclude

# Use a log file: don't rely on SSH scrollback.
set -o pipefail
PYTHONUNBUFFERED=1 python3 mvp_server.py \
  --host 0.0.0.0 --ports 11701,11702,11704 \
  --routes routes.remote.local.json \
  --cert certs/server.crt --key certs/server.key \
  2>&1 | tee "logs/lobby-$(date +%Y%m%d-%H%M%S).log"
```

Test **one Switch first**. Confirm it reaches Online, then try one private lobby and note exact in-game result. Keep the process running briefly to record follow-up calls, then Ctrl+C. If behavior is improved, perform a second separate test with the other Switch; don't combine attempts until per-user state exists. Check log for brand-new unimplemented GUIDs, RedLynx requests, diagnostics, and any heartbeat unregister.

Undo the lobby 404-vs-Success experiment (stop server first):

```bash
python3 enable_lobby_rpc_probe.py routes.remote.local.json --undo
# Or restore the exact saved config:
cp -p routes.remote.prelobby.local.json routes.remote.local.json
```

Avoid committing the private routes JSON, certificate/private key or the potentially identity-bearing log file. The test helper preserves all preexisting typed presence settings, public endpoints, TLS and nine heartbeat version values.

### After the A/B test

If lobby still fails, **stop adding blanket 0800 replies**. Use the client protobuf descriptors and executable callback/xrefs to implement actual stateful `Squad` / `Matchmake` responses bound to independently identified sessions and consistent status polling. Current `PostLogin` instance globally tracks heartbeat generation/state and `presence_connected` across users, which is insufficient to independently model two participants. RedLynx needs separate framing/response research on port 11701. Gameplay transport remains unimplemented.

## Separate Nintendo console UI branch

Atmosphère 1.11.2 release notes explicitly add basic support for system FW 22.5.0. Nintendo's WWZ product page says some online modes require Nintendo Switch Online membership. The eShop prompt may be an account/entitlement/system-app issue, not a Hydra RPC error. Compare on both consoles game/update/DLC versions, selected Nintendo profile, entitlement status and exact UI message before asserting a firmware or Atmosphère fix. We do **not** require updating the OLED console to test the WWZ backend.
